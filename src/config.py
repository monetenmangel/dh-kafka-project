"""
Konfiguration für die Negationsanalyse – Kafka vs. Vergleichskorpus
"""

# ── spaCy ─────────────────────────────────────────────────────
SPACY_MODEL_DE = "de_core_news_lg"

# ── Kafka-Korpus ──────────────────────────────────────────────
# Unterordner in data/kafka_korpus/, die einbezogen werden
KAFKA_ORDNER = ["roman_fragmente", "erzählungen", "dramen"]

# Werke ausschließen (Dateiname ohne .txt), z.B. ["grosser_laerm"]
KAFKA_EXCLUDE: list[str] = []

# ── Vergleichskorpus ─────────────────────────────────────────
# Einschlussliste (Dateiname ohne .txt) — leer = alle Dateien
VERGLEICH_INCLUDE: list[str] = []

# Ausschlussliste (Dateiname ohne .txt) - Gedichte
VERGLEICH_EXCLUDE: list[str] = ["Beer-Hofmann_SchlafliedFürMirjam", "Ehrenstein_DerMenschSchreit", "George_DerKrieg", "George_DerSiebenteRing", "George_DerSternDesBundes", "George_DerTeppichDesLebens",
                                "Heym_DerGottDerStadt", "Heym_DerKrieg", "Heym_DieStadt", "Heym_DieStädte", "Lasker-Schüler_MeinBlauesKlavier.txt", "Lasker-Schüler_Sphinx", "Lasker-Schüler_Weltende",
                                "Lasker-Schüler_EinAlterTibetteppich", "Rilke_BuchDerBilder", "Rilke_DasStundenBuch", "Rilke_DerPanther", "Rilke_DieSonetteAnOrpheus", "Trakl_Gedichte", "Trakl_Dichtungen",
                                "Trakl_SebastianImTraum", "Trakl_Grodek", "Werfel_GesängeAusDenDreiReichen", "Werfel_WirSind"]

# Präfix-basierter Ausschluss (Kafka-Duplikate im Vergleichskorpus)
VERGLEICH_EXCLUDE_PREFIXES: list[str] = ["Kafka_"]

# ── Filter ────────────────────────────────────────────────────
# Werke mit weniger Sätzen werden übersprungen (geschätzt via Regex, billig)
MIN_SAETZE: int = 0 # 20 sehr gute Ergebnisse

# ── Backward Compatibility ───────────────────────────────────
RELEVANTE_ORDNER = KAFKA_ORDNER