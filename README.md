# 📦 annotate-box

Annotation environment in a box. Spin up a complete, production-ready annotation project in minutes.

**What you get:**
- [Label Studio](https://labelstud.io) deployed with TLS and a public URL
- Schema builder — describe your labels in YAML, get the right Label Studio config
- Data preprocessing — sentence splitting, format conversion, deduplication
- Automated git exports — versioned annotation history on a schedule
- Optional AI assistant — an OpenClaw agent on Discord to help your team

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/brezgis/annotate-box
cd annotate-box
cp config.example.yaml config.yaml
# Edit config.yaml with your project details

# 2. Deploy (on your server)
./setup.sh

# 3. Import your data
python3 scripts/import_data.py --config config.yaml --input ./data/

# 4. Start annotating
# Visit https://your-project.duckdns.org
```

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

And get the correct Label Studio XML config automatically. Supports:
- **Span labeling** (sentence-level or character-level)
- **Document classification** (single or multi-label)
- **Named entity recognition**
- **Sequence labeling**
- **Pairwise comparison**

### Data Preprocessing

Import from common formats:
- Plain text files (`.txt`)
- CSV / TSV
- JSON / JSONL
- CoNLL format

Optional transforms:
- Sentence splitting (NLTK punkt)
- Tokenization
- Deduplication
- Shuffling with seed (for unbiased annotation order)

### Automated Exports

Annotation snapshots committed to git on a schedule:

```yaml
export:
  schedule: daily
  time: "22:00"
  format: json
```

Every export includes annotation counts, so your git log reads like a progress tracker:
```
Annotation export 2026-02-18 (calibration: 3/3, main: 47/200)
```

### Deployment

Two options:

**Docker Compose** (recommended):
```bash
docker compose up -d
```

**Bare metal** (for existing servers):
```bash
./setup.sh --bare
```

Both handle:
- Label Studio installation and configuration
- Nginx reverse proxy
- TLS via Let's Encrypt (with DuckDNS or custom domain)
- Systemd service (bare metal) or container restart policy (Docker)

### AI Project Assistant (Optional)

If you run [OpenClaw](https://github.com/openclaw/openclaw), you can add a Discord bot that:
- Answers questions about the annotation schema
- Troubleshoots Label Studio issues
- Monitors annotation progress
- Runs exports on demand

## Project Structure

```
annotate-box/
├── config.yaml              # Your project configuration
├── setup.sh                 # Deployment script
├── docker-compose.yaml      # Docker deployment
├── scripts/
│   ├── import_data.py       # Data preprocessing + import
│   ├── export.sh            # Git export script
│   ├── schema_builder.py    # YAML → Label Studio XML
│   └── iaa.py               # Inter-annotator agreement metrics
├── templates/
│   ├── nginx.conf.j2        # Nginx config template
│   ├── label-studio.service # Systemd service template
│   └── agent/               # OpenClaw agent templates
│       ├── SOUL.md
│       ├── AGENTS.md
│       └── TOOLS.md
└── examples/
    └── ted-talks/           # Example config from our TED project
```

## Requirements

- A server (VPS, home server, etc.) with Python 3.9+
- A domain name OR free DuckDNS subdomain
- Docker (recommended) OR bare metal with root access

## License

MIT

---

*Born from a real annotation project at Brandeis University. Built by Anna Brezgis and Claude.*
