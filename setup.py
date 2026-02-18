#!/usr/bin/env python3
"""annotate-box setup wizard.

Interactive CLI that walks you through configuring your annotation project.
Generates config.yaml, Label Studio XML, docker-compose.yaml, and optionally
OpenClaw agent workspace files.
"""
import os
import sys
import json
import random
import string
import textwrap
from pathlib import Path

# Schema builder import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from schema_builder import build_schema

# ─── Colors & formatting ────────────────────────────────────────────────────

BOLD = '\033[1m'
DIM = '\033[2m'
GREEN = '\033[92m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'
PINK = '\033[95m'

def banner():
    print(f"""
{CYAN}{BOLD}  ╔══════════════════════════════════════╗
  ║  📦  annotate-box  setup wizard      ║
  ╚══════════════════════════════════════╝{RESET}
""")

def section(title):
    print(f"\n{BOLD}{CYAN}── {title} ──{RESET}\n")

def success(msg):
    print(f"  {GREEN}✓{RESET} {msg}")

def warn(msg):
    print(f"  {YELLOW}⚠{RESET} {msg}")

def info(msg):
    print(f"  {DIM}{msg}{RESET}")

def ask(prompt, default=None):
    """Ask a question with optional default."""
    if default:
        prompt_str = f"  {prompt} {DIM}[{default}]{RESET}: "
    else:
        prompt_str = f"  {prompt}: "
    answer = input(prompt_str).strip()
    return answer if answer else default

def choose(prompt, options, default=1):
    """Multiple choice question. Returns (index, label)."""
    print(f"  {prompt}")
    for i, (label, desc) in enumerate(options, 1):
        marker = f"{CYAN}▸{RESET}" if i == default else " "
        print(f"  {marker} [{i}] {label}{f' — {DIM}{desc}{RESET}' if desc else ''}")
    while True:
        choice = input(f"  {DIM}Choose [1-{len(options)}] (default {default}):{RESET} ").strip()
        if not choice:
            choice = str(default)
        try:
            idx = int(choice)
            if 1 <= idx <= len(options):
                return idx, options[idx - 1][0]
        except ValueError:
            pass
        print(f"  {RED}Please enter a number 1-{len(options)}{RESET}")

def confirm(prompt, default=True):
    """Yes/no question."""
    hint = "Y/n" if default else "y/N"
    answer = input(f"  {prompt} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer in ('y', 'yes')

def random_password(length=16):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


# ─── Default color palette ───────────────────────────────────────────────────

COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    "#F1948A", "#82E0AA", "#F8C471", "#AED6F1", "#D7BDE2",
]


# ─── Main wizard ─────────────────────────────────────────────────────────────

def run_wizard():
    banner()

    config = {}

    # ── Project info ──
    section("Project")
    config['project'] = {
        'name': ask("Project name", "My Annotation Project"),
        'description': ask("Short description", ""),
    }

    # ── Deployment ──
    section("Deployment")
    deploy_idx, deploy_choice = choose("Where will this run?", [
        ("Local Docker", "docker compose up on this machine"),
        ("Remote server", "VPS or cloud server with a public IP"),
        ("Config only", "just generate files, I'll deploy myself"),
    ])
    config['_deploy'] = deploy_idx

    # ── Domain ──
    config['server'] = {'port': 8093}

    if deploy_idx in (1, 2):
        section("Domain & TLS")
        domain_idx, _ = choose("How should people reach your server?", [
            ("Free DuckDNS subdomain", "e.g. my-project.duckdns.org"),
            ("I have a domain", "e.g. annotations.example.com"),
            ("Localhost only", "no public access, no TLS"),
        ])

        if domain_idx == 1:
            subdomain = ask("DuckDNS subdomain (without .duckdns.org)")
            token = ask("DuckDNS token (from duckdns.org/install.jsp)")
            config['server']['duckdns'] = {
                'subdomain': subdomain or 'my-project',
                'token': token or 'YOUR_DUCKDNS_TOKEN',
            }
            config['_domain'] = f"{config['server']['duckdns']['subdomain']}.duckdns.org"
        elif domain_idx == 2:
            domain = ask("Your domain name")
            config['server']['domain'] = domain or 'annotations.example.com'
            config['_domain'] = config['server']['domain']
        else:
            config['_domain'] = 'localhost'

    # ── Admin account ──
    section("Admin Account")
    info("This creates the first Label Studio user (project admin).")
    admin_email = ask("Admin email")
    admin_pass = ask("Admin password (leave blank to auto-generate)")
    if not admin_pass:
        admin_pass = random_password()
        info(f"Generated password: {admin_pass}")
    config['server']['admin'] = {
        'email': admin_email or 'admin@example.com',
        'password': admin_pass,
    }

    # ── Team ──
    section("Team")
    team = [{'name': 'Admin', 'email': config['server']['admin']['email'], 'role': 'admin'}]
    info("Add team members who will annotate. They'll create their own accounts at the URL.")
    while True:
        name = ask("Team member name (blank to finish)")
        if not name:
            break
        email = ask(f"  {name}'s email")
        team.append({'name': name, 'email': email or ''})
    config['team'] = team
    if len(team) > 1:
        success(f"{len(team)} team members ({', '.join(t['name'] for t in team)})")
    else:
        info("Solo annotator mode — you can add more later in config.yaml")

    # ── Annotation schema ──
    section("Annotation Schema")

    task_idx, task_choice = choose("What type of annotation?", [
        ("Span labeling", "highlight text and assign a label (NER, rhetoric, etc.)"),
        ("Document classification", "assign one or more labels to a whole document"),
        ("Named entity recognition", "label entities in text (people, places, etc.)"),
        ("Pairwise comparison", "compare two texts and choose one"),
    ])

    schema_type_map = {1: 'span', 2: 'classification', 3: 'ner', 4: 'pairwise'}
    schema_type = schema_type_map[task_idx]
    granularity = None

    if schema_type == 'span':
        gran_idx, _ = choose("Granularity?", [
            ("Sentence-level", "click a sentence to label it — great for discourse/rhetoric"),
            ("Character-level", "highlight any span of text — more flexible, more work"),
        ])
        granularity = 'sentence' if gran_idx == 1 else 'character'

    multi_label = False
    if schema_type == 'classification':
        ml_idx, _ = choose("Classification mode?", [
            ("Single label", "each document gets exactly one label"),
            ("Multi-label", "each document can get multiple labels"),
        ])
        multi_label = (ml_idx == 2)

    # Labels
    print()
    info("Define your labels. Enter them comma-separated.")
    info("Example: METAPHOR, IRONY, REPETITION, NONE, UNCERTAIN")
    label_input = ask("Labels")

    labels = []
    if label_input:
        for i, name in enumerate(label_input.split(',')):
            name = name.strip().upper()
            if name:
                labels.append({
                    'name': name,
                    'hotkey': str(i + 1) if i < 9 else '',
                    'color': COLORS[i % len(COLORS)],
                })
    else:
        # Default labels
        labels = [
            {'name': 'POSITIVE', 'hotkey': '1', 'color': '#4ECDC4'},
            {'name': 'NEGATIVE', 'hotkey': '2', 'color': '#FF6B6B'},
            {'name': 'NEUTRAL', 'hotkey': '3', 'color': '#95A5A6'},
        ]
        info("Using default labels: POSITIVE, NEGATIVE, NEUTRAL")

    # Add descriptions
    if confirm("Add descriptions to each label?", default=False):
        for label in labels:
            desc = ask(f"  Description for {label['name']}")
            if desc:
                label['description'] = desc

    config['schema'] = {
        'type': schema_type,
        'labels': labels,
    }
    if granularity:
        config['schema']['granularity'] = granularity
    if multi_label:
        config['schema']['multi_label'] = True

    # Max annotations
    max_ann = ask("Max annotations per item (for agreement, usually 1-3)", "1")
    try:
        config['schema']['max_annotations'] = int(max_ann)
    except:
        config['schema']['max_annotations'] = 1

    success(f"Schema: {schema_type}" + (f" ({granularity})" if granularity else "") +
            f" with {len(labels)} labels")

    # ── Data ──
    section("Data")

    fmt_idx, fmt_choice = choose("What format is your data in?", [
        ("Plain text files", ".txt files, one document per file"),
        ("CSV / TSV", "spreadsheet format with a text column"),
        ("JSON", "JSON files with a text field"),
        ("JSONL", "one JSON object per line"),
        ("I'll import later", "skip data setup for now"),
    ])

    fmt_map = {1: 'text', 2: 'csv', 3: 'json', 4: 'jsonl', 5: None}
    data_fmt = fmt_map[fmt_idx]

    config['data'] = {}
    if data_fmt:
        config['data']['format'] = data_fmt
        config['data']['source'] = ask("Data directory", "./data/")

        if schema_type == 'span' and granularity == 'sentence':
            config['data']['sentence_split'] = confirm("Auto-split text into sentences?", default=True)

        config['data']['shuffle'] = confirm("Randomize order? (prevents annotation bias)", default=True)
        if config['data']['shuffle']:
            config['data']['shuffle_seed'] = 42

        max_items = ask("Max items to import (blank for all)")
        if max_items:
            try:
                config['data']['max_items'] = int(max_items)
            except:
                pass

    # ── Export ──
    section("Automated Exports")
    info("Auto-export annotations to git on a schedule.")

    export_idx, _ = choose("Export schedule?", [
        ("Daily", "once a day, versioned in git"),
        ("Hourly", "every hour"),
        ("Manual only", "I'll run exports myself"),
    ])

    schedule_map = {1: 'daily', 2: 'hourly', 3: 'manual'}
    config['export'] = {'schedule': schedule_map[export_idx], 'format': 'json'}

    if export_idx == 1:
        config['export']['time'] = ask("Export time (24h format)", "22:00")
        config['export']['timezone'] = ask("Timezone", "America/New_York")

    config['export']['git'] = {'enabled': confirm("Enable git commits?", default=True)}
    if config['export']['git']['enabled']:
        config['export']['git']['push'] = confirm("Auto-push to remote?", default=False)

    # ── Guidelines ──
    section("Annotation Guidelines")
    info("If you have a guidelines document (markdown), place it at guidelines.md")
    info("in the project root. It will be shown to annotators in Label Studio.")
    if os.path.exists('guidelines.md'):
        success("Found guidelines.md — will be included in project setup")
    else:
        info("No guidelines.md found — you can add one later.")

    # ── Agent ──
    section("AI Project Assistant (Optional)")
    info("An AI bot on Discord that helps your team with annotation questions,")
    info("troubleshoots Label Studio issues, and monitors progress.")
    info("Requires OpenClaw (https://github.com/openclaw/openclaw).")
    print()

    use_agent = confirm("Set up an AI assistant?", default=False)
    config['agent'] = {'enabled': use_agent}
    if use_agent:
        guild_id = ask("Discord server (guild) ID")
        channel = ask("Discord channel name", "general")
        config['agent']['discord'] = {
            'guild_id': guild_id or 'YOUR_GUILD_ID',
            'channel': channel,
        }

    # ─── Generate files ──────────────────────────────────────────────────────

    section("Generating Files")

    # 1. config.yaml
    write_config_yaml(config)
    success("config.yaml")

    # 2. Label Studio XML
    xml = build_schema(config['schema'])
    Path('label-config.xml').write_text(xml)
    success("label-config.xml (Label Studio schema)")

    # 3. docker-compose.yaml (if Docker deployment)
    if config.get('_deploy') in (1, 2):
        write_docker_compose(config)
        success("docker-compose.yaml")

        write_caddyfile(config)
        success("Caddyfile (reverse proxy + TLS)")

    # 4. .env file
    write_env(config)
    success(".env (credentials — gitignored)")

    # 5. Agent workspace (if enabled)
    if config['agent']['enabled']:
        write_agent_files(config)
        success("agent/ workspace (SOUL.md, AGENTS.md, TOOLS.md)")

    # 6. Export script
    if config['export']['git']['enabled']:
        os.makedirs('exports', exist_ok=True)
        success("exports/ directory")

    # 7. Data directory
    if config.get('data', {}).get('source'):
        os.makedirs(config['data']['source'], exist_ok=True)
        success(f"{config['data']['source']} directory")

    # ─── Summary ─────────────────────────────────────────────────────────────

    section("Done! 🎉")
    print(f"""  {BOLD}Your annotation project is configured.{RESET}

  {BOLD}Next steps:{RESET}""")

    step = 1
    if config.get('data', {}).get('format'):
        print(f"  {step}. Put your data files in {CYAN}{config['data']['source']}{RESET}")
        print(f"     Then run: {CYAN}python3 scripts/import_data.py --config config.yaml{RESET}")
        step += 1

    if config.get('_deploy') in (1, 2):
        print(f"  {step}. Start the server: {CYAN}docker compose up -d{RESET}")
        step += 1
        domain = config.get('_domain', 'localhost')
        if domain != 'localhost':
            print(f"  {step}. Visit {CYAN}https://{domain}{RESET} and log in")
        else:
            print(f"  {step}. Visit {CYAN}http://localhost:{config['server']['port']}{RESET} and log in")
        step += 1
    elif config.get('_deploy') == 3:
        print(f"  {step}. Deploy Label Studio using the generated configs")
        step += 1

    print(f"  {step}. Import data via the Label Studio UI or API")
    step += 1
    print(f"  {step}. Share the URL with your team and start annotating!")
    step += 1

    if config['agent']['enabled']:
        print(f"\n  {PINK}🤖 Agent setup:{RESET}")
        print(f"  Copy agent/ to your OpenClaw workspace and configure the gateway.")
        print(f"  See agent/README.md for details.")

    print(f"\n  {DIM}Config saved to config.yaml — edit anytime and re-run setup.py{RESET}")
    print()


# ─── File writers ────────────────────────────────────────────────────────────

def write_config_yaml(config):
    """Write config.yaml (manually to preserve comments and ordering)."""
    lines = []
    lines.append("# annotate-box configuration")
    lines.append(f"# Generated by setup wizard\n")

    # Project
    lines.append("project:")
    lines.append(f'  name: "{config["project"]["name"]}"')
    if config['project'].get('description'):
        lines.append(f'  description: "{config["project"]["description"]}"')

    # Server
    lines.append("\nserver:")
    if 'duckdns' in config.get('server', {}):
        lines.append("  duckdns:")
        lines.append(f'    subdomain: {config["server"]["duckdns"]["subdomain"]}')
        lines.append(f'    token: {config["server"]["duckdns"]["token"]}')
    elif 'domain' in config.get('server', {}):
        lines.append(f'  domain: {config["server"]["domain"]}')
    lines.append(f'  port: {config["server"].get("port", 8093)}')
    lines.append("  admin:")
    lines.append(f'    email: {config["server"]["admin"]["email"]}')
    lines.append(f'    password: {config["server"]["admin"]["password"]}')

    # Team
    lines.append("\nteam:")
    for member in config.get('team', []):
        role_str = f"\n    role: {member['role']}" if member.get('role') else ""
        lines.append(f'  - name: {member["name"]}')
        lines.append(f'    email: {member.get("email", "")}')
        if member.get('role'):
            lines.append(f'    role: {member["role"]}')

    # Schema
    lines.append("\nschema:")
    lines.append(f'  type: {config["schema"]["type"]}')
    if config["schema"].get("granularity"):
        lines.append(f'  granularity: {config["schema"]["granularity"]}')
    if config["schema"].get("multi_label"):
        lines.append(f'  multi_label: true')
    lines.append(f'  max_annotations: {config["schema"].get("max_annotations", 1)}')
    lines.append("  labels:")
    for label in config["schema"]["labels"]:
        lines.append(f'    - name: {label["name"]}')
        if label.get('hotkey'):
            lines.append(f'      hotkey: "{label["hotkey"]}"')
        lines.append(f'      color: "{label["color"]}"')
        if label.get('description'):
            lines.append(f'      description: "{label["description"]}"')

    # Data
    if config.get('data', {}).get('format'):
        lines.append("\ndata:")
        lines.append(f'  format: {config["data"]["format"]}')
        lines.append(f'  source: {config["data"].get("source", "./data/")}')
        if config["data"].get("sentence_split"):
            lines.append("  sentence_split: true")
        if config["data"].get("shuffle"):
            lines.append("  shuffle: true")
            lines.append(f'  shuffle_seed: {config["data"].get("shuffle_seed", 42)}')
        if config["data"].get("max_items"):
            lines.append(f'  max_items: {config["data"]["max_items"]}')

    # Export
    lines.append("\nexport:")
    lines.append(f'  schedule: {config["export"]["schedule"]}')
    lines.append(f'  format: {config["export"].get("format", "json")}')
    if config["export"].get("time"):
        lines.append(f'  time: "{config["export"]["time"]}"')
    if config["export"].get("timezone"):
        lines.append(f'  timezone: "{config["export"]["timezone"]}"')
    lines.append("  git:")
    lines.append(f'    enabled: {str(config["export"]["git"]["enabled"]).lower()}')
    if config["export"]["git"].get("push"):
        lines.append(f'    push: {str(config["export"]["git"]["push"]).lower()}')

    # Agent
    lines.append("\nagent:")
    lines.append(f'  enabled: {str(config["agent"]["enabled"]).lower()}')
    if config["agent"].get("discord"):
        lines.append("  discord:")
        lines.append(f'    guild_id: "{config["agent"]["discord"]["guild_id"]}"')
        lines.append(f'    channel: {config["agent"]["discord"]["channel"]}')

    Path('config.yaml').write_text('\n'.join(lines) + '\n')


def write_docker_compose(config):
    """Generate docker-compose.yaml with Label Studio + Caddy."""
    domain = config.get('_domain', 'localhost')
    port = config['server'].get('port', 8093)

    compose = f"""# annotate-box docker compose
# Usage: docker compose up -d

services:
  postgres:
    image: postgres:16-alpine
    container_name: annotate-box-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=labelstudio
      - POSTGRES_USER=labelstudio
      - POSTGRES_PASSWORD=${{POSTGRES_PASSWORD:-labelstudio}}
    volumes:
      - pg-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U labelstudio"]
      interval: 10s
      timeout: 5s
      retries: 5

  label-studio:
    image: heartexlabs/label-studio:latest
    container_name: annotate-box-ls
    restart: unless-stopped
    ports:
      - "127.0.0.1:{port}:{port}"
    environment:
      - LABEL_STUDIO_HOST=${{LABEL_STUDIO_HOST}}
      - LABEL_STUDIO_PORT={port}
      - DJANGO_DB=default
      - POSTGRE_NAME=labelstudio
      - POSTGRE_USER=labelstudio
      - POSTGRE_PASSWORD=${{POSTGRES_PASSWORD:-labelstudio}}
      - POSTGRE_HOST=postgres
      - POSTGRE_PORT=5432
      - LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
      - LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT=/label-studio/files
      - CSRF_TRUSTED_ORIGINS=${{CSRF_TRUSTED_ORIGINS}}
    env_file:
      - .env
    volumes:
      - ls-data:/label-studio/data
      - ls-files:/label-studio/files
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:{port}/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  caddy:
    image: caddy:2-alpine
    container_name: annotate-box-caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy-data:/data
      - caddy-config:/config
    depends_on:
      label-studio:
        condition: service_healthy

volumes:
  pg-data:
  ls-data:
  ls-files:
  caddy-data:
  caddy-config:
"""
    Path('docker-compose.yaml').write_text(compose)


def write_caddyfile(config):
    """Generate Caddyfile for reverse proxy + automatic TLS."""
    domain = config.get('_domain', 'localhost')
    port = config['server'].get('port', 8093)

    if domain == 'localhost':
        caddyfile = f"""http://localhost {{
    reverse_proxy label-studio:{port}
}}
"""
    else:
        caddyfile = f"""{domain} {{
    reverse_proxy label-studio:{port}
}}
"""
    Path('Caddyfile').write_text(caddyfile)


def write_env(config):
    """Generate .env file with credentials."""
    domain = config.get('_domain', 'localhost')
    port = config['server'].get('port', 8093)

    if domain == 'localhost':
        host = f"http://localhost:{port}"
        origins = host
    else:
        host = f"https://{domain}"
        origins = host

    pg_pass = random_password(20)
    env_lines = [
        f"# annotate-box environment",
        f"LABEL_STUDIO_HOST={host}",
        f"LABEL_STUDIO_PORT={port}",
        f"CSRF_TRUSTED_ORIGINS={origins}",
        f"",
        f"# Database",
        f"POSTGRES_PASSWORD={pg_pass}",
        f"",
        f"# Admin credentials",
        f"LABEL_STUDIO_USERNAME={config['server']['admin']['email']}",
        f"LABEL_STUDIO_PASSWORD={config['server']['admin']['password']}",
    ]

    if 'duckdns' in config.get('server', {}):
        env_lines.append(f"")
        env_lines.append(f"# DuckDNS")
        env_lines.append(f"DUCKDNS_TOKEN={config['server']['duckdns']['token']}")

    Path('.env').write_text('\n'.join(env_lines) + '\n')


def write_agent_files(config):
    """Generate OpenClaw agent workspace files."""
    os.makedirs('agent', exist_ok=True)

    project_name = config['project']['name']
    domain = config.get('_domain', 'localhost')
    team_list = '\n'.join(
        f"- **{m['name']}**{' (' + m['email'] + ')' if m.get('email') else ''}"
        + (f" — {m['role']}" if m.get('role') else '')
        for m in config.get('team', [])
    )

    schema_rows = "| Label | Hotkey | Description |\n|-------|--------|-------------|\n"
    for label in config['schema']['labels']:
        schema_rows += f"| {label['name']} | {label.get('hotkey', '')} | {label.get('description', '')} |\n"

    url = f"https://{domain}" if domain != 'localhost' else f"http://localhost:{config['server'].get('port', 8093)}"

    # SOUL.md
    soul_template = Path('templates/agent/SOUL.md').read_text()
    soul = soul_template.replace('{{PROJECT_NAME}}', project_name)
    soul = soul.replace('{{TEAM_LIST}}', team_list)
    soul = soul.replace('{{SCHEMA_TABLE}}', schema_rows)
    soul = soul.replace('{{LABEL_STUDIO_URL}}', url)
    Path('agent/SOUL.md').write_text(soul)

    # AGENTS.md
    Path('agent/AGENTS.md').write_text(f"""# AGENTS.md

## Every Session
1. Read `SOUL.md` — your identity and project context
2. Help the team with annotation questions and Label Studio issues

## What You Do
- Answer schema questions
- Troubleshoot Label Studio
- Run exports when asked
- Monitor annotation progress
""")

    # TOOLS.md
    Path('agent/TOOLS.md').write_text(f"""# Tools

## Label Studio
- **URL:** {url}
- **Admin:** See .env for credentials
- **API auth:** Session cookies (GET /user/login → CSRF → POST login)

## Export
Run `bash scripts/export.sh` to export and commit annotations.

## Server
```bash
docker compose ps        # check status
docker compose logs -f   # watch logs
docker compose restart   # restart everything
```
""")

    Path('agent/README.md').write_text(f"""# Agent Setup

To use the AI assistant, you need [OpenClaw](https://github.com/openclaw/openclaw).

1. Copy the `agent/` directory to your OpenClaw workspace
2. Configure the gateway to bind to your Discord server
3. The agent will respond in your project's Discord channel

See OpenClaw docs for gateway configuration details.
""")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    try:
        run_wizard()
    except KeyboardInterrupt:
        print(f"\n\n  {DIM}Setup cancelled.{RESET}\n")
        sys.exit(1)
