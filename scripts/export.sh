#!/bin/bash
# Export annotations from Label Studio and commit to git
# Usage: ./export.sh [config.yaml]
set -euo pipefail

CONFIG="${1:-config.yaml}"
TIMESTAMP=$(date +%Y-%m-%d_%H%M)

# Parse config (requires yq or python fallback)
parse_yaml() {
    python3 - "$CONFIG" "$1" <<'PYEOF'
import yaml, sys
config_path = sys.argv[1]
dotted_key = sys.argv[2]
with open(config_path) as f:
    c = yaml.safe_load(f)
val = c
for key in dotted_key.split('.'):
    val = val.get(key, {}) if isinstance(val, dict) else ''
print(val if val else '')
PYEOF
}

LS_HOST="${LS_HOST:-http://127.0.0.1:$(parse_yaml server.port)}"
LS_EMAIL="$(parse_yaml server.admin.email)"
LS_PASSWORD="$(parse_yaml server.admin.password)"
EXPORT_DIR="${EXPORT_DIR:-./exports}"
EXPORT_FORMAT="$(parse_yaml export.format)"
EXPORT_FORMAT="${EXPORT_FORMAT:-JSON}"

mkdir -p "$EXPORT_DIR"

echo "[$(date)] Starting annotation export..."

# Authenticate with Label Studio (session cookie auth)
COOKIE_JAR=$(mktemp)
trap "rm -f $COOKIE_JAR" EXIT

# If Label Studio is remote (via SSH), the caller should set LS_HOST
# For local installs, it's http://127.0.0.1:PORT

# 1. Get CSRF token
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" "${LS_HOST}/user/login" -o /dev/null

CSRF=$(grep csrftoken "$COOKIE_JAR" | awk '{print $NF}')

# 2. Login
curl -s -c "$COOKIE_JAR" -b "$COOKIE_JAR" -X POST "${LS_HOST}/user/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -H "X-CSRFToken: $CSRF" \
    -H "Referer: ${LS_HOST}/user/login" \
    -d "email=${LS_EMAIL}&password=${LS_PASSWORD}" -o /dev/null

CSRF=$(grep csrftoken "$COOKIE_JAR" | awk '{print $NF}')

# 3. Get all projects
PROJECTS=$(curl -s -b "$COOKIE_JAR" \
    -H "Referer: ${LS_HOST}/" \
    "${LS_HOST}/api/projects")

# 4. Export each project
echo "$PROJECTS" | python3 -c "
import json, sys
projects = json.load(sys.stdin)
if isinstance(projects, dict):
    projects = projects.get('results', [])
for p in projects:
    print(f\"{p['id']}|{p['title']}\")
" | while IFS='|' read -r project_id project_title; do
    # Sanitize title for filename
    safe_title=$(echo "$project_title" | tr ' /' '_-' | tr -cd 'a-zA-Z0-9_-')
    outfile="${EXPORT_DIR}/project_${project_id}_${safe_title}.json"

    curl -s -b "$COOKIE_JAR" \
        -H "Referer: ${LS_HOST}/" \
        "${LS_HOST}/api/projects/${project_id}/export?exportType=${EXPORT_FORMAT}" \
        -o "$outfile"

    # Count annotations
    count=$(python3 - "$outfile" <<'PYEOF' 2>/dev/null || echo "?/?")
import json, sys
data = json.load(open(sys.argv[1]))
annotated = sum(1 for t in data if t.get('annotations'))
total = len(data)
print(f'{annotated}/{total}')
PYEOF

    echo "  Project ${project_id} (${project_title}): ${count} annotated"
done

# 5. Git commit if enabled and there are changes
if [ -d .git ] || [ -d ../.git ]; then
    git add exports/ 2>/dev/null || true
    if ! git diff --cached --quiet 2>/dev/null; then
        git commit -m "Annotation export ${TIMESTAMP}"
        echo "  ✓ Committed to git"

        # Auto-push if configured
        PUSH=$(parse_yaml export.git.push)
        if [ "$PUSH" = "True" ] || [ "$PUSH" = "true" ]; then
            git push 2>/dev/null && echo "  ✓ Pushed to remote" || echo "  ⚠ Push failed"
        fi
    else
        echo "  No changes to commit"
    fi
fi

echo "[$(date)] Export complete"
