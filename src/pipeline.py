"""
pipeline.py — Orchestrierung der Negationsanalyse-Pipeline

Koordiniert morphologische und syntaktische Analyse und erzeugt drei DataFrames:
  df_saetze:  Metadaten pro Satz       (Kern-Tabelle)
  df_morpho:  un-Wort-Vorkommen        (Token-Ebene)
  df_syntax:  Doppelnegationen          (Fund-Ebene)

Nutzung:
    import spacy, config, pipeline
    nlp = spacy.load(config.SPACY_MODEL_DE)
    df_saetze, df_morpho, df_syntax = pipeline.run_pipeline(nlp)
"""

import os
import re
import pandas as pd

import config
from morpho_analyse import find_negated_lemmas, find_valid_un_lemmas  # noqa: F401
from syntax_analyse import find_double_negations

# Re-Exporte für Abwärtskompatibilität
from morpho_analyse import (  # noqa: F401
    NEGATIVE_PREFIX_CONFIG,
    NEGATIVE_SUFFIX_CONFIG,
    NEGATIVE_PREFIXES,
    LEXICALIZED_EXCEPTIONS,
    UN_FALSE_POSITIVES,
    ist_bekanntes_deutsches_wort,
)
from syntax_analyse import (  # noqa: F401
    NEGATION_TOKENS,
    CLAUSE_BOUNDARY_DEPS,
)


# ═══════════════════════════════════════════════════════════════
#  FILE I/O
# ═══════════════════════════════════════════════════════════════

def read_txt_file(file_path: str) -> str:
    """Liest eine Textdatei und gibt den Inhalt als String zurück."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def build_werk_list(base_path: str) -> list[dict]:
    """
    Baut die Werkliste anhand der Config.

    Returns:
        Liste von dicts mit {werk_id, autor, korpus, pfad}
    """
    werke = []

    # ── Kafka-Korpus ──
    kafka_base = os.path.join(base_path, "data", "kafka_korpus")
    for ordner in config.KAFKA_ORDNER:
        ordner_path = os.path.join(kafka_base, ordner)
        if not os.path.isdir(ordner_path):
            print(f"  ⚠ Ordner nicht gefunden: {ordner_path}")
            continue
        for f in sorted(os.listdir(ordner_path)):
            if not f.endswith(".txt"):
                continue
            name = os.path.splitext(f)[0]
            if name in config.KAFKA_EXCLUDE:
                continue
            werke.append({
                "werk_id": name,
                "autor": "Kafka",
                "korpus": "kafka",
                "pfad": os.path.join(ordner_path, f),
            })

    # ── Vergleichskorpus ──
    vergleich_base = os.path.join(base_path, "data", "Vergleichskorpus", "corpus")
    if os.path.isdir(vergleich_base):
        for f in sorted(os.listdir(vergleich_base)):
            if not f.endswith(".txt"):
                continue
            name = os.path.splitext(f)[0]
            # Präfix-Ausschluss (z.B. Kafka-Duplikate)
            if any(name.startswith(p) for p in config.VERGLEICH_EXCLUDE_PREFIXES):
                continue
            # Expliziter Ausschluss
            if name in config.VERGLEICH_EXCLUDE:
                continue
            # Einschluss-Filter (leer = alle)
            if config.VERGLEICH_INCLUDE and name not in config.VERGLEICH_INCLUDE:
                continue
            # Autor aus Dateiname: "ThMann_Zauberberg1" → "ThMann"
            autor = name.split("_")[0] if "_" in name else name
            werke.append({
                "werk_id": name,
                "autor": autor,
                "korpus": "vergleich",
                "pfad": os.path.join(vergleich_base, f),
            })

    return werke


# ═══════════════════════════════════════════════════════════════
#  PIPELINE
# ═══════════════════════════════════════════════════════════════

def process_werk(werk_info: dict, nlp) -> tuple[list, list, list]:
    """
    Verarbeitet ein einzelnes Werk.

    Returns:
        (saetze_rows, morpho_rows, syntax_rows)
    """
    text = werk_info.pop("_text_cache", None) or read_txt_file(werk_info["pfad"])

    # max_length dynamisch anpassen
    if len(text) > nlp.max_length:
        nlp.max_length = len(text) + 1000

    doc = nlp(text)

    werk_id = werk_info["werk_id"]
    autor = werk_info["autor"]
    korpus = werk_info["korpus"]

    # Negierte Lemmas validieren (Type-Level) — Präfixe + Suffixe
    valid_negated = find_negated_lemmas(doc)

    # Sätze durchlaufen
    sentences = list(doc.sents)
    n_sents = len(sentences)

    saetze_rows = []
    morpho_rows = []

    for satz_idx, sent in enumerate(sentences):
        alpha_tokens = [t for t in sent if t.is_alpha]

        saetze_rows.append({
            "werk_id": werk_id,
            "autor": autor,
            "korpus": korpus,
            "satz_id": satz_idx,
            "satz": sent.text.strip(),
            "n_tokens": len(alpha_tokens),
            "n_chars": len(sent.text.strip()),
            "satz_position": round(satz_idx / max(n_sents - 1, 1), 6),
        })

        # Negierte Wort-Vorkommen (Token-Ebene)
        for token in sent:
            if not token.is_alpha:
                continue
            lemma = token.lemma_.lower()
            if lemma in valid_negated:
                info = valid_negated[lemma]
                morpho_rows.append({
                    "werk_id": werk_id,
                    "satz_id": satz_idx,
                    "token_text": token.text,
                    "lemma": lemma,
                    "affix_typ": info["affix_typ"],
                    "affix": info["affix"],
                    "rest": info["rest"],
                    "pos_tag": info["pos"],
                    "validierung": info["validierung"],
                })

    # Doppelnegationen
    dn_results = find_double_negations(doc)
    syntax_rows = [{
        "werk_id": werk_id,
        "satz_id": dn["satz_idx"],
        "typ": dn["typ"],
        "negation_1": dn["negation_1"],
        "negation_2": dn["negation_2"],
        "prefixed_word": dn["prefixed_word"],
        "clause_head": dn["clause_head"],
        "dep_relation": dn["dep_relation"],
    } for dn in dn_results]

    return saetze_rows, morpho_rows, syntax_rows


def run_pipeline(
    nlp,
    base_path: str = None,
    korpus: str = "beide",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Führt die vollständige Analyse-Pipeline aus.

    Args:
        nlp:        geladenes spaCy-Modell
        base_path:  Projektroot (default: ../ relativ zu diesem Modul)
        korpus:     "kafka", "vergleich" oder "beide"

    Returns:
        (df_saetze, df_morpho, df_syntax)
    """
    if base_path is None:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    werke = build_werk_list(base_path)

    # Filter nach Korpus
    if korpus != "beide":
        werke = [w for w in werke if w["korpus"] == korpus]

    # ── Satzschätzung: Werke unter Threshold rausfiltern ──
    if config.MIN_SAETZE > 0:
        before = len(werke)
        werke_filtered = []
        for w in werke:
            text = read_txt_file(w["pfad"])
            est = len(re.findall(r'[.!?]+[\s\n]+', text))
            if est >= config.MIN_SAETZE:
                w["_text_cache"] = text  # Text cachen, damit wir ihn nicht doppelt lesen
                werke_filtered.append(w)
            else:
                print(f"  ⏭ {w['werk_id']} übersprungen (~{est} Sätze < {config.MIN_SAETZE})")
        werke = werke_filtered
        print(f"  → {before - len(werke)} Werke gefiltert (MIN_SAETZE={config.MIN_SAETZE})")

    n_kafka = sum(1 for w in werke if w["korpus"] == "kafka")
    n_vergl = sum(1 for w in werke if w["korpus"] == "vergleich")
    print(f"Pipeline: {len(werke)} Werke ({n_kafka} Kafka, {n_vergl} Vergleich)")

    all_saetze, all_morpho, all_syntax = [], [], []

    for i, werk in enumerate(werke):
        print(f"  [{i+1}/{len(werke)}] {werk['werk_id']}", end=" … ")
        s, m, x = process_werk(werk, nlp)
        all_saetze.extend(s)
        all_morpho.extend(m)
        all_syntax.extend(x)
        print(f"{len(s)} Sätze, {len(m)} un-Wörter, {len(x)} Doppelneg.")

    df_saetze = pd.DataFrame(all_saetze)
    df_morpho = pd.DataFrame(all_morpho) if all_morpho else pd.DataFrame(
        columns=["werk_id", "satz_id", "token_text", "lemma", "affix_typ",
                 "affix", "rest", "pos_tag", "validierung"]
    )
    df_syntax = pd.DataFrame(all_syntax) if all_syntax else pd.DataFrame(
        columns=["werk_id", "satz_id", "typ", "negation_1", "negation_2",
                 "prefixed_word", "clause_head", "dep_relation"]
    )

    print(f"\n✓ {len(df_saetze)} Sätze | {len(df_morpho)} neg. Affixe | {len(df_syntax)} Doppelnegationen")
    return df_saetze, df_morpho, df_syntax

