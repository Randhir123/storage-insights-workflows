# AGENTS.md

This repository automates:

> **OpenAPI spec → Arazzo workflow(s) → Python SDK via Speakeasy → Workflow-friendly Python wrapper code**

Codex should treat this file as the **primary** instruction set when operating on this repo.

---

## Project goals

1. Use the provided **OpenAPI document** and instructions, create **Arazzo workflows**.  
2. Use **Speakeasy** to generate an idiomatic **Python SDK** from that OpenAPI document.  
3. Build a small **Python wrapper layer** that exposes high-level “workflow functions” aligned with the Arazzo workflows (rather than raw endpoints).  
4. Keep the flow **repeatable** so SDK can be regenerated safely when the OpenAPI spec changes, while **preserving wrapper code**.

---

## Repository structure

```
openapi/
  openapi.yaml                # Source OpenAPI (single source of truth)

workflows/
  *.arazzo.yaml               # Arazzo workflow specs, derived from openapi.yaml

sdks/python/                  # Generated Python SDK (DO NOT HAND-EDIT)
  ...

src/
  config.py                   # Base URL, auth, retry/timeouts, etc.
  workflows/
    __init__.py
    *.py                      # High-level wrappers that call the generated SDK

tests/
  test_*.py                   # Integration-style tests exercising wrappers/flows
```

> If any folder/file is missing, Codex should create it.

---

## Setup commands

Codex should assume these commands for a local dev run.

### 1) Python environment

Use Python 3.10+ and a virtual environment:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows
# .venv\Scripts\activate

pip install -U pip
```

### 2) Tooling

Install the CLIs used by this repo:

```bash
# Speakeasy CLI (preferred install script; puts binary under ~/.speakeasy/bin)
curl -fsSL https://go.speakeasy.com/cli-install.sh | sh
~/.speakeasy/bin/speakeasy --version

# (Optional) OpenAPI CLI for validating OpenAPI + Arazzo
# macOS:
brew install openapi
# or Linux:
# curl -fsSL https://get.openapicli.com | bash -s -- -b ~/.local/bin
```

### 3) Speakeasy auth (first time only)

```bash
~/.speakeasy/bin/speakeasy auth login
```

---
## Configuration & secrets

- **Base URL:** set via `SI_BASE_URL` (default used by `src/config.py` if unset).  
- **Auth:** pass IBM Storage Insights API Key via `SI_API_KEY` (exported to `x-api-key` header).  
- **Do not** commit keys to the repo. Use environment variables locally; use **GitHub Actions secrets** in CI.

Example local `.env` (not committed):

```
SI_BASE_URL=https://dev.insights.ibm.com
SI_API_KEY=***redacted***
```

---
## Core tasks Codex SHOULD perform (in order)

### A) Validate OpenAPI and Arazzo

```bash
# Validate the OpenAPI spec
openapi spec validate ./openapi/openapi.yaml

# Validate all Arazzo workflow files
for f in workflows/*.arazzo.yaml; do
  openapi arazzo validate "$f"
done
```

If validation fails, **stop and report** errors instead of proceeding.

---

### B) Generate/refresh the Python SDK (idempotent)

```bash
~/.speakeasy/bin/speakeasy run   --schema ./openapi/openapi.yaml   --target sdk   --lang python   --out ./sdks/python
```

- Treat `sdks/python/` as generated code.  
- **Never** hand-edit files under `sdks/python/`.

---

### C) Generate runnable workflow tests/code from Arazzo (optional but recommended)

We keep workflow specs in `workflows/*.arazzo.yaml`. Speakeasy can derive runnable tests/code from these.

```bash
# Lint Arazzo files (again, fast-fail)
~/.speakeasy/bin/speakeasy lint arazzo -f workflows

# Generate & run tests (uses mock by default; see “Real env” below)
~/.speakeasy/bin/speakeasy test
```
