# dh-kafka-project

Quantitative Negationsanalyse von Franz Kafkas Prosa im Vergleich mit deutschsprachiger Literatur der klassischen Moderne. Das Projekt erkennt morphologisch negierte Wörter (Präfixe wie *un-*, *miss-*; Suffixe wie *-los*, *-frei*) sowie syntaktische und morpho-syntaktische Doppelnegationen mittels spaCy-NLP und statistischer Auswertung.

---

## Voraussetzungen

- **Python 3.12**

---

## Installation & Einrichtung

### 1. Repository klonen

```bash
git clone https://github.com/BenMangel/dh-kafka-project.git
cd dh-kafka-project
```

### 2. Virtuelle Umgebung erstellen & aktivieren

**Windows:**
```bash
py -3.12 -m venv venv
```

**macOS / Linux:**
```bash
python3.12 -m venv venv
```

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
source venv/bin/activate
```

### 3. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### 4. spaCy-Sprachmodell herunterladen, wenn nicht schon aus requirements.txt

```bash
python -m spacy download de_core_news_lg
```

---

## Projektstruktur

```
dh-kafka-project/
├── README.md
├── requirements.txt
├── .gitignore
├── data/
│   ├── kafka_korpus/          # Kafka-Texte (Erzählungen, Romanfragmente, …)
│   │   ├── erzählungen/
│   │   ├── roman_fragmente/
│   │   ├── briefe/
│   │   ├── dramen/
│   │   ├── notizsammlungen/
│   │   └── tagebücher/
│   └── Vergleichskorpus/      # Texte anderer Autoren der klass. Moderne
│       └── corpus/
├── src/
│   ├── config.py              # Zentrale Konfiguration (Modell, Werkauswahl, Filter)
│   ├── morpho_analyse.py      # Morphologische Analyse (negierte Affixe)
│   ├── syntax_analyse.py      # Syntaktische Analyse (Doppelnegationen)
│   ├── pipeline.py            # Orchestrierung: baut Werkliste, ruft Analysen auf
│   ├── analysis.ipynb         # Jupyter-Notebook: Pipeline + Visualisierung
│   └── syntaktische_analysis.ipynb  # Notebook: Detail-Analyse Doppelnegationen
└── output/                    # Erzeugte CSVs und Plots (via .gitignore ignoriert)
    ├── df_saetze.csv
    ├── df_morpho.csv
    └── df_syntax.csv
```

### Module im Detail

| Datei | Aufgabe |
|---|---|
| `config.py` | Sprachmodell, Ordner-/Werkauswahl, Ausschlüsse, Mindest-Satzanzahl |
| `morpho_analyse.py` | Erkennung negierender Präfixe (`un-`, `miss-`, `il-`, `ir-`, `nicht-`) und Suffixe (`-los`, `-frei`), Validierung gegen wordfreq + Suffix-Heuristik |
| `syntax_analyse.py` | Identifikation von Doppelnegationen im Dependenzbaum (Clause-Head-Logik, gleicher Teilsatz) |
| `pipeline.py` | Datei-I/O, Werkliste aufbauen, `process_werk()` und `run_pipeline()` – koordiniert beide Analysemodule und erzeugt drei DataFrames |

---

## Nutzung

### Pipeline im Notebook ausführen

Die Notebooks in `src/` sind der primäre Einstiegspunkt. Nach Aktivierung der venv:

```bash
cd src
jupyter notebook analysis.ipynb
```

Die erste Code-Zelle lädt spaCy, die Pipeline-Zelle erzeugt die drei DataFrames und speichert sie als CSV in `output/`.

### Pipeline programmatisch nutzen

```python
import spacy
import config
import pipeline

nlp = spacy.load(config.SPACY_MODEL_DE)
df_saetze, df_morpho, df_syntax = pipeline.run_pipeline(nlp)
```

---

## Erzeugte Daten

| DataFrame | Inhalt |
|---|---|
| `df_saetze` | Eine Zeile pro Satz – Metadaten (Werk, Autor, Korpus, Token-/Zeichenzahl, Position) |
| `df_morpho` | Eine Zeile pro negiertem Wort-Vorkommen – Affix-Typ, Stamm, POS-Tag, Validierung |
| `df_syntax` | Eine Zeile pro Doppelnegation – Typ, beteiligte Tokens, Clause-Head, Dep-Relation |

---

## Konfiguration

Alle Parameter werden in `src/config.py` gesetzt:

- **`SPACY_MODEL_DE`** – spaCy-Modell (Standard: `de_core_news_lg`)
- **`KAFKA_ORDNER`** – welche Unterordner des Kafka-Korpus einbezogen werden
- **`KAFKA_EXCLUDE`** – einzelne Werke ausschließen
- **`VERGLEICH_INCLUDE` / `VERGLEICH_EXCLUDE`** – Werkfilter fürs Vergleichskorpus
- **`MIN_SAETZE`** – Mindestanzahl geschätzter Sätze, um ein Werk einzubeziehen