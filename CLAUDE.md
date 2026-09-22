# CLAUDE.md

Durable guidance for agents working in this repository.

## Commands

```bash
# Install dependencies
uv sync

# Run local mode through the dev runner
./scripts/local-run-dev-sync.sh --mode local

# Run cloud mode locally against dev AWS-backed config
./scripts/local-run-dev-sync.sh --mode cloud --uuid <uuid>

# Run tests
uv run python -m unittest discover test/ -v
uv run coverage run -m unittest discover -s test -v
uv run coverage report -m

# Lint
make lint
# or individually:
black src/ lambda_function.py --line-length 120
flake8 src/ lambda_function.py --max-line-length 120
prettier --write .

# Public push safety (recommended before pushing public branches)
./scripts/check_public_push_safety.sh
```

## Architecture

### Two execution modes

`src/config/config.py:generate_config()` is the single branch point. `APP_MODE` must be set explicitly.

- **Local** (`APP_MODE=local`): loads the v2 mapping-domain document from `config/local.mapping-domain.json`; secrets are loaded from environment variables.
- **Cloud** (`APP_MODE=cloud`): requires a UUID, reads settings/Task sources/Calendar mappings from the mapping-domain table, and reads OAuth tokens from their UUID-keyed tables.

Do not infer mode from UUID. Do not fallback to `token/*.json`. Do not commit secrets.

Local configuration/credentials live in `.env.local`: `NOTION_TOKEN`, `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, and `GOOGLE_CALENDAR_REFRESH_TOKEN`. Cloud reuses the non-secret `GOOGLE_CALENDAR_CLIENT_ID`, loads OAuth tokens from DynamoDB, and resolves secrets through `GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH` and `TOKEN_ENCRYPTION_KEY_SSM_PATH`.

Tokens may be plaintext or `enc:v1:` encrypted. Use `src/utils/token_crypto.py:decrypt_token_if_encrypted()` at token read boundaries; `decrypt_token()` stays strict. In cloud mode, token encryption keys are resolved from SSM via `TOKEN_ENCRYPTION_KEY_SSM_PATH`; local mode may still use plaintext `TOKEN_ENCRYPTION_KEY`.

`MappingDomainConfig` is the only configuration boundary. It returns one isolated runtime setting per active Task source with exactly one active Calendar mapping and fails closed on missing, malformed, stale, or ambiguous state.

### Request flow

```
Lambda trigger (SQS / EventBridge)
  └─ lambda_function.lambda_handler
       └─ src/main.main(uuid)
            ├─ generate_config(uuid)
            ├─ MappingDomainConfig → active source settings
            ├─ NotionToken + GoogleToken
            └─ for each source: NotionService + GoogleService → sync
```

### Sync logic (`src/sync/sync.py`)

`project_notion_to_google_calendar` is the only sync direction. Notion is authoritative for task content and scheduling.

1. Fetch the authoritative Notion tasks for the configured source/window.
2. Build deterministic provider projection identity from owner + source + mapping + task + target.
3. For each Notion task:
   - deletion flag set → delete only the owned Google projection;
   - otherwise → upsert the owned Google projection.
4. Inventory only mapping-tagged Google events in the configured target and retire owned projections whose Notion task is no longer present.
5. Never create/update/delete Notion tasks from Google Calendar state.
6. Before every Google mutation, revalidate mapping-domain state plus current Notion and Google OAuth bindings.
7. Untagged, incompletely tagged, or wrongly tagged provider events are not silently adopted.
8. Hard cap: skip a source run if authoritative Notion task input exceeds `SYNC_TASK_LIMIT`.

### DynamoDB tables

Runtime tables (set via env vars):

- `DYNAMODB_MAPPING_DOMAIN_TABLE` — sole sync-configuration authority; owner partition plus `SourceMappingsIndex`
- `DYNAMODB_USER_TABLE` — sync-log summary only; never configuration
- `DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE` — Google OAuth tokens (refreshed in-place)
- `DYNAMODB_NOTION_OAUTH_TOKEN_TABLE` — Notion API token (encrypted as `enc:v1:…`)
- `DYNAMODB_SYNC_LOGS_TABLE` — sync result logs with TTL

The worker consumes provider property IDs, derives offsets from `NotionSettings.timeZone`, and routes by persisted mapping/Calendar identity. Distinct Task sources may share one Calendar because provider materializations are isolated by owner/source/mapping/task/target identity.

### Token encryption

Notion and Google OAuth tokens may use `src/utils/token_crypto.py`. The `enc:v1:` prefix signals an encrypted value; in cloud mode the crypto key comes from SSM (`TOKEN_ENCRYPTION_KEY_SSM_PATH`), while local mode can read `TOKEN_ENCRYPTION_KEY`.

## Deployment

- **`dev` push** → auto-deploy to `dev-fn-notion-sync-gcal` Lambda via `.github/workflows/deploy-dev-lambda.yml`
- **`master` push** → semantic release only (git tag + GitHub Release), no Lambda deploy
- **Production** → manual `workflow_dispatch` only, workflow currently disabled in `.github/workflows/disabled/`

CI validates with `uv sync --frozen --dev`, Black, Flake8, unittest, secret scan, and workflow guardrails before any image build or Lambda update.

**Safety invariant**: `master` push must never build an ECR image or update Lambda. Only immutable image tags (`vX.Y.Z`, `sha-<short_sha>`) are allowed in production deploys.
