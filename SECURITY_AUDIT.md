# Security Audit — annotate-box

**Auditor:** Hex (security specialist)
**Date:** 2026-02-17
**Scope:** All source files in the annotate-box project

---

## CRITICAL

### C1. Shell Injection via YAML Config Values in `export.sh`

**File:** `scripts/export.sh`, lines using `parse_yaml`
**Severity:** CRITICAL

The `parse_yaml()` function interpolates `$CONFIG` and `$1` directly into a Python string using single quotes inside a bash heredoc. The config file path and dotted key are injected into Python code via bash variable expansion. More critically, the **values read from config** (email, password, etc.) are used unquoted in shell contexts:

```bash
LS_EMAIL="$(parse_yaml server.admin.email)"
LS_PASSWORD="$(parse_yaml server.admin.password)"
```

Then used in:
```bash
-d "email=${LS_EMAIL}&password=${LS_PASSWORD}"
```

If a password contains characters like `"`, `$`, `` ` ``, or `$(...)`, bash will interpret them. A password like `$(rm -rf /)` or `` `whoami` `` would execute arbitrary commands.

Additionally, `$outfile` is constructed from the project title and used unquoted in the `python3 -c` heredoc:
```bash
data = json.load(open('$outfile'))
```
A project title containing `'` would break out of the Python string.

**Fix:** See patch file.

### C2. Shell Injection via `$outfile` in Export Loop

**File:** `scripts/export.sh`
**Severity:** CRITICAL

```bash
count=$(python3 -c "
import json
data = json.load(open('$outfile'))
...")
```

The `$outfile` variable is derived from `$project_title` (user-controlled via Label Studio). A project named `'); import os; os.system('id` would execute arbitrary code.

**Fix:** Pass `$outfile` as an argument to Python, not interpolated into code. See patch.

---

## HIGH

### H1. YAML Injection in Generated `config.yaml`

**File:** `setup.py`, `write_config_yaml()`
**Severity:** HIGH

User input (project name, description, email, password, team member names, domain, etc.) is written directly into YAML using f-strings with no escaping:

```python
lines.append(f'  name: "{config["project"]["name"]}"')
lines.append(f'    password: {config["server"]["admin"]["password"]}')
```

- The **password** field is written **without quotes**. A password like `true` becomes a YAML boolean. A password like `key: value\nnew_field: injected` breaks YAML structure.
- The **project name** is double-quoted but a name containing `"` would break the quoting.
- Team member names are written unquoted — a name like `name: evil\n    role: admin` would inject fields.

**Fix:** Use the `yaml` library's `yaml.dump()` or properly quote/escape all values. At minimum, always quote strings and escape internal quotes.

### H2. Credentials Written to `config.yaml` in Plaintext

**File:** `setup.py`, `write_config_yaml()`
**Severity:** HIGH

The admin password is written in plaintext to `config.yaml`. While `.env` is gitignored, **`config.yaml` is NOT gitignored**. Users who commit their repo will push credentials to their remote.

The example config (`config.example.yaml`) contains `password: changeme123` and the TED talks example also has `password: changeme123`.

**Fix:** 
1. Add `config.yaml` to `.gitignore` (it's already there ✓ — confirmed).
2. Remove the password from `config.yaml` and reference `.env` instead, or add a big warning comment.
3. Change example passwords to clearly placeholder values and add warnings.

*Note: On re-check, `config.yaml` IS in `.gitignore`. Downgrading concern — but credentials are still duplicated across `config.yaml` and `.env`, increasing exposure surface.*

**Revised severity:** MEDIUM (since config.yaml is gitignored)

### H3. DuckDNS Token in Plaintext Config

**File:** `setup.py`, `write_config_yaml()` and `write_env()`
**Severity:** HIGH

The DuckDNS token is written to both `config.yaml` and `.env`. The token grants DNS control over the subdomain. `config.yaml` stores it unquoted — the same YAML injection issues from H1 apply. If the token leaks, an attacker can redirect the domain to their own server and intercept credentials.

**Fix:** Store DuckDNS token only in `.env`, reference it via environment variable in docker-compose.

---

## MEDIUM

### M1. Caddyfile Injection via Domain Name

**File:** `setup.py`, `write_caddyfile()`
**Severity:** MEDIUM

```python
caddyfile = f"""{domain} {{
    reverse_proxy label-studio:{port}
}}"""
```

The domain is user input with no validation. A domain like `evil.com { } :80 { respond "pwned" } #` would inject arbitrary Caddy directives. This could redirect traffic, serve malicious content, or disable TLS.

**Fix:** Validate domain against a regex like `^[a-zA-Z0-9][a-zA-Z0-9.-]+[a-zA-Z0-9]$`.

### M2. Docker Compose Injection via Port

**File:** `setup.py`, `write_docker_compose()`
**Severity:** MEDIUM

The port value is user-supplied and written directly into the compose YAML. While `port` defaults to 8093, a user could provide a value like `8093" \n    privileged: true` to inject Docker options.

*In practice, the port comes from `config['server'].get('port', 8093)` and defaults to int, so exploitation requires modifying the code flow. Lower likelihood.*

**Fix:** Validate port is an integer in range 1-65535.

### M3. No Input Validation on Any User Input

**File:** `setup.py`
**Severity:** MEDIUM

The `ask()` function returns raw user input with only `.strip()`. No validation is performed on:
- Email addresses (could contain shell metacharacters)
- Project names (could contain quotes, newlines)
- Domain names (could contain spaces, special chars)
- Passwords (could contain YAML-breaking characters)

All of these flow into generated config files.

**Fix:** Add validation functions for each input type (email regex, domain regex, safe-string check for names).

### M4. Weak Default Password in Examples

**File:** `config.example.yaml`, `examples/ted-talks/config.yaml`
**Severity:** MEDIUM

Both use `password: changeme123` which users may deploy without changing.

**Fix:** Use a clearly invalid placeholder like `CHANGE_ME_BEFORE_DEPLOYING` or generate a random password in the example.

### M5. Cookie Jar Created with Default umask

**File:** `scripts/export.sh`
**Severity:** MEDIUM

```bash
COOKIE_JAR=$(mktemp)
```

`mktemp` creates files with 0600 permissions on most systems (safe), but this is umask-dependent. The cookie jar contains a valid session cookie that grants admin access to Label Studio.

**Fix:** Explicitly set permissions: `COOKIE_JAR=$(mktemp) && chmod 600 "$COOKIE_JAR"`

### M6. Password Logged to Terminal

**File:** `setup.py`
**Severity:** MEDIUM

```python
admin_pass = random_password()
info(f"Generated password: {admin_pass}")
```

Auto-generated passwords are printed to the terminal (and potentially logged in shell history/scrollback). Users using `script` or terminal logging will have credentials in plaintext logs.

**Fix:** Consider writing to `.env` only and telling users to check `.env` for the password, rather than printing it.

---

## LOW

### L1. No Memory Limit on JSON/CSV Loading

**File:** `scripts/import_data.py`
**Severity:** LOW

`json.load(fh)` loads entire files into memory. A maliciously large JSON file (multi-GB) would cause OOM. However, this is a local CLI tool run by the project owner, so the threat model is limited.

**Fix:** Consider streaming JSON parsing for large files, or add a file size check.

### L2. Glob Patterns Traverse Subdirectories

**File:** `scripts/import_data.py`
**Severity:** LOW

```python
for f in sorted(source.glob('**/*.txt')):
```

The `**` glob recurses into all subdirectories. If `source` is set to `/` or `../../`, it would read files outside the project. This is a local tool where the user controls the config, so it's a usability concern more than a security one.

**Fix:** Resolve the source path and verify it's within the project directory.

### L3. CSV Dialect Not Restricted

**File:** `scripts/import_data.py`
**Severity:** LOW

`csv.DictReader` with default settings. CSV bomb attacks (fields with excessive quoting/escaping) could cause performance issues but not code execution.

### L4. `iaa.py` Uses `json.load` — No Code Injection Risk

**File:** `scripts/iaa.py`
**Severity:** INFO

The file only uses `json.load()` and does arithmetic on the parsed data. There is no `eval()`, `exec()`, or dynamic code execution. JSON parsing in Python's standard library is safe against code injection. **No vulnerability found.**

### L5. Trap Only Covers EXIT

**File:** `scripts/export.sh`
**Severity:** LOW

```bash
trap "rm -f $COOKIE_JAR" EXIT
```

This is actually correct — `EXIT` trap fires on normal exit and most signals. However, `SIGKILL` can't be trapped, so the cookie jar may persist in that case. Acceptable risk.

---

## INFO

### I1. `.env` Is Properly Gitignored ✓

The `.gitignore` includes `.env`. Good.

### I2. `schema_builder.py` Uses `xml.sax.saxutils.escape()` ✓

Label names are properly XML-escaped using `escape()` before insertion into the XML template. This prevents XML injection via label names. **Well done.**

### I3. No Hardcoded Secrets Found ✓

No API keys, tokens, or passwords are hardcoded in source code. Example files use obvious placeholders.

### I4. No Debug Endpoints Found ✓

No Flask/Django debug modes, no test endpoints, no backdoors detected.

### I5. Generated Files Have Appropriate Permissions

Docker compose, Caddyfile, and config files are written with default permissions. `.env` should ideally be 0600 but the Docker workflow typically requires group-readable files.

### I6. `set -euo pipefail` in export.sh ✓

Good defensive scripting. Unset variables will cause errors rather than silent empty expansion (though this interacts with the injection issues above — `set -u` helps but doesn't prevent injection in quoted contexts).

---

## Summary

| Severity | Count | Items |
|----------|-------|-------|
| CRITICAL | 2 | C1, C2 — Shell injection in export.sh |
| HIGH | 1 | H3 — DuckDNS token exposure |
| MEDIUM | 6 | M1–M6 |
| LOW | 5 | L1–L5 |
| INFO | 6 | I1–I6 |

**The most urgent fixes are C1 and C2** — the shell/Python injection vulnerabilities in `export.sh`. These are exploitable if a Label Studio project has a crafted title, or if config values contain shell metacharacters (which is likely with passwords).
