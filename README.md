# storage-insights-workflows
IBM Storage Insights Workflows
=======
# Storage Insights Workflows

Turn the IBM Storage Insights OpenAPI description into executable workflows and Python helpers. This repo shows the full path from downloading the upstream spec to running an opinionated workflow that lists block storage systems and surfaces the top systems by volume count.

## Repository map

```
AGENTS.md                       # canonical repo instructions
openapi/openapi.yaml            # upstream IBM Storage Insights spec (source of truth)
src/config.py                   # env-driven configuration (base URL, tenant ID, API key)
src/auth/token_manager.py       # API token creation + caching (x-api-token)
src/workflows/                  # workflow-friendly Python helpers
workflows/                      # Arazzo specs derived from the OpenAPI document
```

## Prerequisites

- Python 3.11+
- [`openapi` CLI](https://github.com/speakeasy-api/openapi) for validating OpenAPI & Arazzo docs (installed via `brew install openapi`)
- [`speakeasy` CLI](https://www.speakeasy.com/openapi) if you plan to regenerate SDKs/tests later
- IBM Storage Insights tenant UUID + API key (stored locally in `creds`, never committed)

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt  # installs requests for the Python wrappers
```

Create a `.env` (ignored) that points to your tenant:

```
SI_BASE_URL=https://dev.insights.ibm.com
SI_TENANT_ID=<tenant uuid>
SI_API_KEY=<api key>
```

The repo already has `creds` → `.env` bootstrapping scripts, but keeping both values here helps when new shells are opened:

```bash
set -a && source .env && set +a
```

## Download/refresh the OpenAPI document

The upstream Swagger UI at `https://dev.insights.ibm.com/restapi/docs/` just bootstraps `/openapi`. Pull the spec locally (idempotent):

```bash
curl -sSf https://dev.insights.ibm.com/openapi -o openapi/openapi.yaml
```

Validate before building workflows or SDKs:

```bash
openapi spec validate openapi/openapi.yaml
```

## Arazzo workflow authoring

`workflows/block-storage-volume-leaders.arazzo.yaml` is a simple example that mirrors the user story “list block storage systems and find the top five by volume count.”

Highlights:

- `sourceDescriptions` references the local OpenAPI file so validation can ensure operation IDs/paths exist.
- The single step, `list-block-storage-systems`, calls `GET /restapi/v1/tenants/{tenant_uuid}/storage-systems` with `storage-type=block`.
- The workflow output exposes `$response.body#/data`, matching the JSON payload returned by the API today.

Validate any workflow edits quickly:

```bash
openapi arazzo validate workflows/block-storage-volume-leaders.arazzo.yaml
```

## Token creation and caching

Storage Insights requires short-lived `x-api-token` headers for almost every endpoint. `src/auth/token_manager.py` encapsulates the flow:

```python
from src.auth.token_manager import TokenManager
from src.config import load_settings

token = TokenManager(load_settings()).get_token()
print(token)
```

- Tokens are minted by calling `POST /restapi/v1/tenants/{tenant_uuid}/token`.
- Responses include an expiration timestamp (15 minute validity). The manager caches to `.cache/token.json` and refreshes 30 seconds before expiry.

## Running the Python workflow helper

`src/workflows/block_storage.py` implements the Arazzo workflow in pure Python: fetch block systems, sort by `volsCount`, slice the top N.

Example usage:

```bash
source .venv/bin/activate
set -a && source .env && set +a
python - <<'PY'
from src.workflows import get_block_storage_volume_leaders
result = get_block_storage_volume_leaders(limit=5)
print("Total systems:", len(result.storage_systems))
for item in result.top_five:
    print(item.get("systemId"), item.get("volsCount"))
PY
```

Sample output (UUIDs masked for the blog post):

```
Total systems: 113
storage-system-1 32821
storage-system-2 32470
storage-system-3 32202
storage-system-4 31882
storage-system-5 30916
```

Under the hood the helper:

1. Loads tenant settings + cached token.
2. Issues `GET /restapi/v1/tenants/{tenant_uuid}/storage-systems?storage-type=block` with `Accept: application/json` and `x-api-token`.
3. Normalizes either `storageSystems` or `data` arrays (IBM has returned both shapes historically).
4. Sorts by `volsCount` (falling back to `volumes_count` if needed) and slices `limit` entries.
5. Returns a dataclass with both the full list and the top subset for downstream automation.

## Verifying raw API calls

If you need to double-check outside Python:

```bash
TOKEN=$(python - <<'PY'
from src.auth.token_manager import TokenManager
from src.config import load_settings
print(TokenManager(load_settings()).get_token())
PY)

curl -sS -X GET \
  -H "Accept: application/json" \
  -H "x-api-token: $TOKEN" \
  "$SI_BASE_URL/restapi/v1/tenants/$SI_TENANT_ID/storage-systems?storage-type=block"
```

## Extending the pattern

1. **Author more workflows**: describe scenarios in `workflows/*.arazzo.yaml` using the same pattern—`sourceDescriptions` + steps + outputs.
2. **Generate SDKs**: once satisfied, run Speakeasy to produce `sdks/python/` and build higher-level wrappers in `src/workflows/` that call the generated client instead of `requests` if you prefer.
3. **Test**: add `tests/test_block_storage.py` style files that stub HTTP responses so future refactors can be validated without hitting the live APIs.

Happy hacking—and feel free to turn these sections into a blog post walking through the entire pipeline: download spec → author workflow → implement helper → run + verify.
