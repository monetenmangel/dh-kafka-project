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

# Ausschlussliste (Dateiname ohne .txt)
VERGLEICH_EXCLUDE: list[str] = []

# Präfix-basierter Ausschluss (Kafka-Duplikate im Vergleichskorpus)
VERGLEICH_EXCLUDE_PREFIXES: list[str] = ["Kafka_"]

# ── Filter ────────────────────────────────────────────────────
# Werke mit weniger Sätzen werden übersprungen (geschätzt via Regex, billig)
MIN_SAETZE: int = 100

# ── Backward Compatibility ───────────────────────────────────
RELEVANTE_ORDNER = KAFKA_ORDNER

# ── Satzlänge Threshold ──────────────────────────────────────
SATZLAENGE_THRESHHOLD = 100