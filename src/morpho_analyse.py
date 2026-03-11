"""
morpho_analyse.py — Morphologische Negationsanalyse

Erkennung morphologisch negierter Wörter (Präfixe wie un-, miss-, …
und Suffixe wie -los, -frei) auf Type- und Token-Ebene.

Erzeugt df_morpho-Zeilen mit Affix-Typ, Stamm, POS-Tag und Validierung.
"""

from wordfreq import word_frequency


# ═══════════════════════════════════════════════════════════════
#  SUFFIX-HEURISTIK (Wort-Erkennung)
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


# ═══════════════════════════════════════════════════════════════
#  FALSE POSITIVES
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  NEGATIONS-AFFIX-KONFIGURATION
# ═══════════════════════════════════════════════════════════════

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
    },
}

# Negierende Suffixe
NEGATIVE_SUFFIX_CONFIG = {
    "los": {
        "min_stem_len": 3,
        "ausnahmen": {
            "los", "lose", "pablos", "quallos", "verflos", "weglos", "ümmerlos"
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


# ═══════════════════════════════════════════════════════════════
#  HILFSFUNKTIONEN
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
#  HAUPTFUNKTION
# ═══════════════════════════════════════════════════════════════

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
