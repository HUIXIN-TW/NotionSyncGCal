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

- **Local** (`APP_MODE=local`): loads structured config from `config/local.notion-setting.json`; secrets are loaded from environment variables.
- **Cloud** (`APP_MODE=cloud`): requires a UUID and reads config/tokens from DynamoDB tables keyed by UUID.

Do not infer mode from UUID. Do not fallback to `token/*.json`. Do not commit secrets.

Local secrets live in `.env.local`: `NOTION_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN`. Cloud uses DynamoDB-backed config/tokens, `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH`, and `TOKEN_ENCRYPTION_KEY_SSM_PATH`.

Tokens may be plaintext or `enc:v1:` encrypted. Use `src/utils/token_crypto.py:decrypt_token_if_encrypted()` at token read boundaries; `decrypt_token()` stays strict. In cloud mode, token encryption keys are resolved from SSM via `TOKEN_ENCRYPTION_KEY_SSM_PATH`; local mode may still use plaintext `TOKEN_ENCRYPTION_KEY`.

All downstream services (`NotionToken`, `NotionConfig`, `GoogleToken`, `GoogleService`) accept the config dict and handle the active mode internally.

### Request flow

```
Lambda trigger (SQS / EventBridge)
  └─ lambda_function.lambda_handler
       └─ src/main.main(uuid)
            ├─ generate_config(uuid)
            ├─ NotionConfig + NotionToken  →  NotionService
            ├─ GoogleToken                →  GoogleService
            └─ sync.synchronize_notion_and_google_calendar(...)
```

### Sync logic (`src/sync/sync.py`)

`synchronize_notion_and_google_calendar` drives the bidirectional sync:

1. Fetch all GCal events and Notion tasks for the configured date window.
2. For each Notion task, match it to a GCal event by `GCal_EventId` property.
   - No GCal ID → create GCal event (`create_gcal`)
   - Deletion flag set → delete GCal event + Notion task (`delete_gcal`)
   - GCal ID found → compare `last_edited_time` vs `updated` to decide `update_gcal` or `update_notion`

3. Remaining unmatched GCal events → create Notion tasks (`create_notion`)
4. Per-task errors are collected in `sync_errors` and returned without stopping the sync.
5. Hard cap: aborts if either side exceeds 250 items (`SYNC_TASK_LIMIT`).

`force_update_*` helpers call `synchronize_notion_and_google_calendar` with `compare_time=False` and one direction disabled.

### DynamoDB tables

Four tables, all keyed by `uuid` (set via env vars):

- `DYNAMODB_USER_TABLE` — user config / local config equivalent
- `DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE` — Google OAuth tokens (refreshed in-place)
- `DYNAMODB_NOTION_OAUTH_TOKEN_TABLE` — Notion API token (encrypted as `enc:v1:…`)
- `DYNAMODB_SYNC_LOGS_TABLE` — sync result logs with TTL

### Token encryption

Notion and Google OAuth tokens may use `src/utils/token_crypto.py`. The `enc:v1:` prefix signals an encrypted value; in cloud mode the crypto key comes from SSM (`TOKEN_ENCRYPTION_KEY_SSM_PATH`), while local mode can read `TOKEN_ENCRYPTION_KEY`.

## Deployment

- **`dev` push** → auto-deploy to `dev-fn-notion-sync-gcal` Lambda via `.github/workflows/deploy-dev-lambda.yml`
- **`master` push** → semantic release only (git tag + GitHub Release), no Lambda deploy
- **Production** → manual `workflow_dispatch` only, workflow currently disabled in `.github/workflows/disabled/`

CI validates with `uv sync --frozen --dev`, Black, Flake8, unittest, secret scan, and workflow guardrails before any image build or Lambda update.

**Safety invariant**: `master` push must never build an ECR image or update Lambda. Only immutable image tags (`vX.Y.Z`, `sha-<short_sha>`) are allowed in production deploys.
