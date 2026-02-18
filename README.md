# 📦 annotate-box

**Annotation is messy.** Setting up a project means deploying a server, configuring label schemas in XML, writing import scripts, wrangling data formats, manually exporting snapshots, and computing agreement metrics by hand. Every team reinvents the same wheel.

**annotate-box is the one-stop shop.** One setup wizard, one URL you send to your annotators, one command to check agreement. Everything else is handled.

### Why use this?

- **Your annotators get one URL.** They sign up, open the project, and start labeling. No local installs, no technical setup on their end.
- **You don't write XML.** Describe your labels in YAML or answer a few wizard questions — the Label Studio config is generated for you.
- **Your annotations are versioned.** Automatic git exports mean you can always go back, compare, and reproduce.
- **Agreement metrics are built in.** One command after calibration tells you if your team agrees — no exporting to spreadsheets and writing scripts.
- **It's free.** Label Studio is open source, DuckDNS gives you a free domain, Let's Encrypt gives you free TLS. The only cost is a server (even a $5/mo VPS works).

### What you get:
- [Label Studio](https://labelstud.io) deployed with TLS and a public URL
- Schema builder — describe your labels in YAML, get the right Label Studio config
- Data preprocessing — sentence splitting, format conversion, shuffling
- Automated git exports — versioned annotation history on a schedule
- Inter-annotator agreement metrics out of the box
- Annotation guidelines support — drop in a `guidelines.md` and it's available to your team
- Optional AI assistant via [OpenClaw](https://github.com/openclaw/openclaw)

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/brezgis/annotate-box
cd annotate-box
pip install -r requirements.txt

# 2. Run the setup wizard
python3 setup.py
# Walks you through: project name, labels, deployment, team, etc.
# Generates config.yaml, docker-compose.yaml, label-config.xml, .env

# 3. Start the server
docker compose up -d

# 4. Import your data
python3 scripts/import_data.py --config config.yaml

# 5. Start annotating!
```

Or configure manually — copy `config.example.yaml` to `config.yaml` and edit it.

## What It Does

### Schema Builder

Describe your annotation task in plain YAML:

```yaml
schema:
  type: span
  granularity: sentence
  labels:
    - name: METAPHOR
      hotkey: "1"
      color: "#FF6B6B"
    - name: IRONY
      hotkey: "2"
      color: "#4ECDC4"
```

Run `python3 scripts/schema_builder.py config.yaml` to generate Label Studio XML. Supports:
- **Span labeling** (sentence-level or character-level)
- **Document classification** (single or multi-label)
- **Named entity recognition**
- **Pairwise comparison**

### Data Preprocessing

Import from common formats:
- Plain text files (`.txt`)
- CSV / TSV
- JSON / JSONL

Optional transforms:
- Sentence splitting (NLTK punkt)
- Shuffling with seed (for unbiased annotation order)
- Length filtering
- Max item limits

### Automated Exports

Annotation snapshots committed to git on a schedule:

```yaml
export:
  schedule: daily
  time: "22:00"
  format: json
  git:
    enabled: true
```

### Deployment

**Docker Compose** (recommended):
```bash
docker compose up -d
```

Includes:
- Label Studio with PostgreSQL backend
- Caddy reverse proxy with automatic TLS
- Support for DuckDNS (free subdomain) or custom domains

### Inter-Annotator Agreement

After your calibration round:

```bash
python3 scripts/iaa.py exports/calibration.json
```

Outputs:
- **Percent agreement** — simple, interpretable
- **Cohen's kappa** — corrects for chance (pairwise)
- **Krippendorff's alpha** — handles multiple annotators, missing data

For sentence-level annotation, it automatically computes per-sentence and per-label agreement. For span tasks, it computes exact-match F1.

```bash
python3 scripts/iaa.py exports/calibration.json --format markdown -o IAA_REPORT.md
```

### AI Project Assistant (Optional)

With [OpenClaw](https://github.com/openclaw/openclaw), you can add a Discord bot that:
- Answers questions about the annotation schema
- Troubleshoots Label Studio issues
- Monitors annotation progress
- Runs exports on demand

## Project Structure

```
annotate-box/
├── setup.py                 # Interactive setup wizard
├── config.example.yaml      # Annotated example config
├── requirements.txt         # Python dependencies
├── scripts/
│   ├── schema_builder.py    # YAML → Label Studio XML
│   ├── import_data.py       # Data preprocessing + import
│   ├── export.sh            # Git export script
│   └── iaa.py               # Inter-annotator agreement
├── templates/
│   └── agent/SOUL.md        # OpenClaw agent template
├── examples/
│   └── ted-talks/config.yaml
└── tests/                   # Unit tests (pytest)
```

**Generated files** (after setup):
- `config.yaml` — your project config (gitignored)
- `docker-compose.yaml` — Docker deployment
- `Caddyfile` — reverse proxy + TLS
- `label-config.xml` — Label Studio schema
- `.env` — credentials (gitignored)

## Requirements

- Python 3.9+
- Docker (for deployment)
- A domain name or free [DuckDNS](https://www.duckdns.org/) subdomain (for public access)

## License

MIT
