"""
pipeline.py — Datenproduktion für die Negationsanalyse

Erzeugt drei DataFrames:
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
from wordfreq import word_frequency

import config


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
#  MORPHOLOGISCHE ANALYSE  (un-Wörter)
# ═══════════════════════════════════════════════════════════════

ADJEKTIV_SUFFIXE = {
    "lich", "ig", "bar", "sam", "haft", "los",
    "reich", "voll", "arm", "fest", "frei", "mäßig",
}
NOMEN_SUFFIXE = {
    "heit", "keit", "ung", "schaft", "tum", "nis",
    "sal", "mut", "sinn", "kraft", "lust",
}
MORPHO_SUFFIXE = ADJEKTIV_SUFFIXE | NOMEN_SUFFIXE

UN_FALSE_POSITIVES = {
    "und", "uns", "unser", "unter", "unten", "ungefähr", "ungeheuer",
    "um", "ungarn", "universal", "universität", "uniform",
    "union", "unitarisch", "unikat", "unison", "ungar",
    "unto", "unique", "unit", "universe", "unrat", "unsr",
    # unter-Komposita
    "unternehmen", "unterbrechen", "unterscheiden", "unterstützen",
    "untersuchen", "unterschied", "unterricht", "unterhaltung",
    "unterhalb", "unterbrechung", "untergang", "untergehen",
    "unterhalten", "unterlassen", "untertauchen", "unterwerfen",
    "unterziehn", "unterziehen",
    # unser-Deklinationsformen
    "unserig", "unsern", "unsere", "unserem", "unseren", "unserer",
    "unseres", "unsrig",
}


def ist_bekanntes_deutsches_wort(wort: str, schwelle: float = 0) -> dict:
    """Prüft ob ein Wort ein bekanntes deutsches Wort ist (wordfreq + Suffix-Heuristik)."""
    wort_lower = wort.lower()
    freq = word_frequency(wort_lower, "de")
    if freq > schwelle:
        return {"bekannt": True, "quelle": "wordfreq", "frequenz": freq}
    for suffix in MORPHO_SUFFIXE:
        if wort_lower.endswith(suffix) and len(wort_lower) > len(suffix) + 2:
            return {"bekannt": True, "quelle": "suffix_heuristik", "frequenz": freq}
    return {"bekannt": False, "quelle": "keine", "frequenz": freq}


def _check_negative_prefix(lemma: str) -> dict | None:
    """
    Prüft ob ein Lemma ein negierendes Präfix hat.

    Returns:
        dict mit {affix_typ, affix, rest, validierung} oder None
    """
    for prefix, cfg in NEGATIVE_PREFIX_CONFIG.items():
        if not lemma.startswith(prefix):
            continue
        rest = lemma[len(prefix):]
        if len(rest) < cfg["min_rest_len"]:
            continue
        if lemma in cfg["ausnahmen"]:
            continue
        # "unter-" Sonderregel: bei Präfix "un" nicht "unter*" matchen
        if prefix == "un" and lemma.startswith("unter"):
            continue
        pruefung = ist_bekanntes_deutsches_wort(rest)
        if pruefung["bekannt"]:
            return {
                "affix_typ": "präfix",
                "affix": prefix,
                "rest": rest,
                "validierung": pruefung["quelle"],
            }
    return None


def _check_negative_suffix(lemma: str) -> dict | None:
    """
    Prüft ob ein Lemma ein negierendes Suffix hat (-los, -frei).

    Returns:
        dict mit {affix_typ, affix, rest, validierung} oder None
    """
    for suffix, cfg in NEGATIVE_SUFFIX_CONFIG.items():
        if not lemma.endswith(suffix):
            continue
        stem = lemma[: -len(suffix)]
        # Bindungs-s/-n/-en entfernen: "hoffnungslos" → "hoffnung"
        for binding in ("s", "n", "en"):
            if stem.endswith(binding) and len(stem) - len(binding) >= cfg["min_stem_len"]:
                stem_clean = stem[: -len(binding)]
                if ist_bekanntes_deutsches_wort(stem_clean)["bekannt"]:
                    stem = stem_clean
                    break
        if len(stem) < cfg["min_stem_len"]:
            continue
        if lemma in cfg["ausnahmen"]:
            continue
        pruefung = ist_bekanntes_deutsches_wort(stem)
        if pruefung["bekannt"]:
            return {
                "affix_typ": "suffix",
                "affix": suffix,
                "rest": stem,
                "validierung": pruefung["quelle"],
            }
    return None


def find_negated_lemmas(doc) -> dict[str, dict]:
    """
    Findet alle morphologisch negierten Lemmas im Dokument (Type-Level).
    Prüft negierende Präfixe (un-, miss-, in-, ...) UND Suffixe (-los, -frei).

    Returns:
        dict: lemma → {"affix_typ", "affix", "rest", "pos", "validierung"}
    """
    relevant_pos = {"ADJ", "NOUN", "ADV", "VERB"}
    valid = {}

    for token in doc:
        if not token.is_alpha:
            continue
        lemma = token.lemma_.lower()
        if lemma in valid:
            continue
        if token.pos_ not in relevant_pos:
            continue
        if lemma in UN_FALSE_POSITIVES:
            continue

        # Präfix prüfen
        result = _check_negative_prefix(lemma)
        if result is None:
            # Suffix prüfen
            result = _check_negative_suffix(lemma)

        if result is not None:
            valid[lemma] = {
                **result,
                "pos": token.pos_,
            }

    return valid


# Abwärtskompatibilität
find_valid_un_lemmas = find_negated_lemmas


# ═══════════════════════════════════════════════════════════════
#  SYNTAKTISCHE ANALYSE  (Doppelnegationen)
# ═══════════════════════════════════════════════════════════════

NEGATION_TOKENS = {
    ("nicht", "PART"): "partikel",
    ("nie", "ADV"): "adverb",
    ("niemals", "ADV"): "adverb",
    ("nirgends", "ADV"): "adverb",
    ("nirgendwo", "ADV"): "adverb",
    ("nichts", "PRON"): "pronomen",
    ("niemand", "PRON"): "pronomen",
    ("kein", "DET"): "determiner",
    ("weder", "CCONJ"): "konjunktion",
}

# Negierende Präfixe mit präfixspezifischen Ausnahmen
NEGATIVE_PREFIX_CONFIG = {
    "un": {
        "min_rest_len": 3,
        "ausnahmen": {
            "ungeheuer", "unfug", "unkosten", "ungeziefer", "umstand",
            "umstände", "uns", "und", "unter", "unten", "ungefähr",
            "unternehmen", "unterbrechen", "unterscheiden", "universal",
            "unsereiner", "unrat",
        },
    },
    "miss": {
        "min_rest_len": 3,
        "ausnahmen": {
            "mission", "mississippi", "mist", "missen",
        },
    },
    "nicht": {
        "min_rest_len": 3,
        "ausnahmen": {
            "nichts",  # ist selbst ein Negationswort, kein Präfix-Wort
        },
    },
    "il": {
        "min_rest_len": 4,
        "ausnahmen": {
            "illustration", "illustrieren", "illusion", "illuster", "illern"
        },
    },
    "ir": {
        "min_rest_len": 4,
        "ausnahmen": {
            "irre", "irren", "irrtum", "irgend", "irgendwo",
            "irgendwie", "irgendwann", "irisch", "ironisch", "ironie", "irdisch", "irdische", 
            "irdisches", "irland", "irländ", "irländer", "irrend", "irrende", "irrest", "irrläufig",
            "irrsinnig", "irrten", "irrtümlich", "irrung"
        },
    }
}

# Negierende Suffixe
NEGATIVE_SUFFIX_CONFIG = {
    "los": {
        "min_stem_len": 3,
        "ausnahmen": {
            "los", "lose", "pablos", "quallos", "verflos", "weglos", "ümmerlos"  # das Wort "los" selbst
        },
    },
    "frei": {
        "min_stem_len": 3,
        "ausnahmen": {
            "frei", "freien", "freier",  # das Adjektiv "frei" selbst
        },
    },
}

# Flache Listen für Abwärtskompatibilität / Schnellzugriff
NEGATIVE_PREFIXES = list(NEGATIVE_PREFIX_CONFIG.keys())
LEXICALIZED_EXCEPTIONS = set()
for _cfg in NEGATIVE_PREFIX_CONFIG.values():
    LEXICALIZED_EXCEPTIONS |= _cfg["ausnahmen"]

CLAUSE_BOUNDARY_DEPS = {"rc", "cp", "cj", "oc", "re"}


def _is_negation(token) -> bool:
    return (token.lemma_.lower(), token.pos_) in NEGATION_TOKENS


def _is_negation_particle(token) -> bool:
    return token.dep_ == "ng"


def _get_clause_head(token):
    current = token
    while current.head != current:
        if current.dep_ in CLAUSE_BOUNDARY_DEPS and current.pos_ in {"VERB", "AUX"}:
            return current
        if current.dep_ == "ROOT":
            return current
        current = current.head
    return current


def _same_clause(token_a, token_b) -> bool:
    return _get_clause_head(token_a) == _get_clause_head(token_b)


def _get_clause_subtree(head_token):
    clause_head = _get_clause_head(head_token)
    return [t for t in head_token.subtree if _get_clause_head(t) == clause_head]


def _has_negative_affix(token) -> bool:
    """Prüft ob ein Token ein negierendes Affix hat (Präfix ODER Suffix)."""
    word = token.text.lower()
    # Präfixe
    for prefix, cfg in NEGATIVE_PREFIX_CONFIG.items():
        if not word.startswith(prefix):
            continue
        rest = word[len(prefix):]
        if len(rest) < cfg["min_rest_len"]:
            continue
        if word in cfg["ausnahmen"]:
            continue
        if prefix == "un" and word.startswith("unter"):
            continue
        return True
    # Suffixe
    for suffix, cfg in NEGATIVE_SUFFIX_CONFIG.items():
        if not word.endswith(suffix):
            continue
        stem = word[: -len(suffix)]
        if len(stem) < cfg["min_stem_len"]:
            continue
        if word in cfg["ausnahmen"]:
            continue
        return True
    return False


# Abwärtskompatibilität
_has_negative_prefix = _has_negative_affix


def find_double_negations(doc) -> list[dict]:
    """
    Findet Doppelnegationen (syntaktisch + morpho-syntaktisch).

    Returns:
        Liste von dicts mit satz_idx, typ, negation_1, negation_2,
        prefixed_word, clause_head, dep_relation
    """
    results = []

    for sent_idx, sent in enumerate(doc.sents):
        negations = [t for t in sent if _is_negation(t) or _is_negation_particle(t)]
        already_paired = set()

        for neg_token in negations:
            if neg_token.i in already_paired:
                continue

            head = neg_token.head
            subtree = _get_clause_subtree(head)

            # ── Syntaktische Doppelnegation ──
            for other in subtree:
                if (other.i != neg_token.i
                        and other.i not in already_paired
                        and (_is_negation(other) or _is_negation_particle(other))
                        and _same_clause(neg_token, other)):
                    results.append({
                        "satz_idx": sent_idx,
                        "typ": "syntaktisch",
                        "negation_1": neg_token.text,
                        "negation_2": other.text,
                        "prefixed_word": None,
                        "clause_head": _get_clause_head(neg_token).text,
                        "dep_relation": neg_token.dep_,
                    })
                    already_paired.add(other.i)

            # ── Morpho-syntaktische Doppelnegation ──
            for other in subtree:
                if (other.i != neg_token.i
                        and _has_negative_affix(other)
                        and _same_clause(neg_token, other)):
                    results.append({
                        "satz_idx": sent_idx,
                        "typ": "morpho-syntaktisch",
                        "negation_1": neg_token.text,
                        "negation_2": None,
                        "prefixed_word": other.text,
                        "clause_head": _get_clause_head(neg_token).text,
                        "dep_relation": neg_token.dep_,
                    })

    return results


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

