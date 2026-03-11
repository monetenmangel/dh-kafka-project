"""
syntax_analyse.py — Syntaktische Negationsanalyse (Doppelnegationen)

Erkennung von Doppelnegationen auf Satzebene:
  - Syntaktische Doppelnegation:       zwei Negationswörter im selben Teilsatz
  - Morpho-syntaktische Doppelnegation: Negationswort + Wort mit negierendem Affix

Erzeugt df_syntax-Zeilen mit Typ, beteiligten Tokens, Clause-Head und Dep-Relation.
"""

from morpho_analyse import NEGATIVE_PREFIX_CONFIG, NEGATIVE_SUFFIX_CONFIG


# ═══════════════════════════════════════════════════════════════
#  NEGATIONS-TOKENS (lexikalische Negationswörter)
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

CLAUSE_BOUNDARY_DEPS = {"rc", "cp", "cj", "oc", "re"}


# ═══════════════════════════════════════════════════════════════
#  HILFSFUNKTIONEN  (Dependenzbaum-Navigation)
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  HAUPTFUNKTION
# ═══════════════════════════════════════════════════════════════

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
