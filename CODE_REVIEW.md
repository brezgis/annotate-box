# Code Review — annotate-box

**Reviewer:** Bea (with Hex on security)  
**Date:** 2026-02-17  
**Scope:** Full codebase review

---

## Critical

### C1. Shell injection in `export.sh` — `parse_yaml` function
**File:** `scripts/export.sh`  
**Lines:** `parse_yaml()` function  
**Issue:** The `$CONFIG` variable and the dotted-path argument `$1` are interpolated directly into a Python string inside a heredoc. If `CONFIG` contains shell metacharacters or a malicious filename, this allows arbitrary code execution.  
**Additionally:** `$outfile` is interpolated unquoted into a Python snippet later in the script (`json.load(open('$outfile'))`), allowing injection via crafted project titles.  
**Fix:** Use proper argument passing (`sys.argv`) instead of string interpolation.  
**Status:** 🔧 FIXED

### C2. `load_csv` uses `|` (bitwise OR) on sorted generators
**File:** `scripts/import_data.py`, `load_csv()`  
**Issue:** `sorted(source.glob('**/*.csv')) | sorted(source.glob('**/*.tsv'))` — the `|` operator on lists raises `TypeError` in Python. This means CSV loading is **completely broken**.  
**Fix:** Use `list(...) + list(...)` or `itertools.chain`.  
**Status:** 🔧 FIXED

---

## Important

### I1. No input validation on source directory (path traversal)
**File:** `scripts/import_data.py`  
**Issue:** `source_dir` from config is passed directly to `Path().glob('**/*')`. A config with `source: /etc/` would happily read system files. Not exploitable remotely (config is local), but defense-in-depth says validate.  
**Fix:** Warn if source is an absolute path outside the project directory.  
**Status:** 🔧 FIXED (warning added)

### I2. No error handling for malformed YAML/JSON
**File:** `scripts/import_data.py`  
**Issue:** `yaml.safe_load(f)` and `json.load(fh)` can throw on malformed input with unhelpful tracebacks. No try/except around file loading.  
**Fix:** Add try/except with user-friendly error messages.  
**Status:** 🔧 FIXED

### I3. No validation of empty labels list
**File:** `scripts/schema_builder.py`  
**Issue:** If `config['labels']` is empty or missing, the builder produces invalid XML with no labels. Should error early.  
**Fix:** Validate labels list is non-empty in `build_schema()`.  
**Status:** 🔧 FIXED

### I4. Admin credentials in generated `config.yaml` (plaintext)
**File:** `setup.py`, `write_config_yaml()`  
**Issue:** Admin password is written in plaintext to `config.yaml`. The `.env` file is gitignored, but `config.yaml` is not — if a user commits it, credentials leak.  
**Fix:** Add `config.yaml` to `.gitignore` (it's already there ✓). Add a comment warning in the generated file. Also add to the example config a note about this.  
**Status:** ✅ Already mitigated (config.yaml is gitignored)

### I5. export.sh project title sanitization is incomplete
**File:** `scripts/export.sh`  
**Issue:** `tr ' /' '_-' | tr -cd 'a-zA-Z0-9_-'` strips most bad chars, but the sanitized title is still used in a path without quoting. The real fix is to quote all variables.  
**Status:** 🔧 FIXED (as part of C1 shell injection fix)

### I6. Shuffling logic has subtle bug
**File:** `scripts/import_data.py`, `main()`  
**Issue:** When `max_items` is set and `shuffle=True`, items are shuffled then truncated. But the "shuffle if not already done" block checks `and not max_items` — this means if `max_items=0`, shuffle is skipped (0 is falsy). Edge case but worth fixing.  
**Fix:** Use explicit `max_items is not None` check.  
**Status:** 🔧 FIXED

---

## Minor

### M1. README references non-existent `./setup.sh`
**File:** `README.md`  
**Issue:** Quick start says `./setup.sh` but the file is `setup.py` (Python wizard). Also mentions `--bare` flag that doesn't exist.  
**Status:** 🔧 FIXED

### M2. README claims features that don't exist
**File:** `README.md`  
**Issue:** Mentions CoNLL format, sequence labeling, tokenization, and deduplication — none of these are implemented.  
**Status:** 🔧 FIXED

### M3. Personal info in README and example config
**File:** `README.md`, `examples/ted-talks/config.yaml`  
**Issue:** README footer says "Born from a real annotation project at Brandeis University. Built by Anna Brezgis and Claude." Example config references "COSI 230B (Annotations) at Brandeis University."  
**Status:** 🔧 FIXED

### M4. Unused import
**File:** `setup.py`  
**Issue:** `textwrap` is imported but never used.  
**Status:** 🔧 FIXED

### M5. `json` imported but unused in `schema_builder.py`
**File:** `scripts/schema_builder.py`  
**Issue:** Not imported, actually. No issue. (False alarm.)  
**Status:** N/A

### M6. CSRF_TRUSTED_ORIGINS may need multiple origins
**File:** `setup.py`, `write_env()`  
**Issue:** Only sets one origin. If Label Studio is accessed via both domain and IP, CSRF will reject the other. Minor since most setups use one URL.  
**Status:** ℹ️ Noted, not fixing (edge case)

---

## Summary

| Severity | Count | Fixed |
|----------|-------|-------|
| Critical | 2 | 2 |
| Important | 6 | 5 |
| Minor | 6 | 4 |
