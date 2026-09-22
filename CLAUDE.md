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

`MappingDomainConfig` is the only configuration boundary. It returns one current-contract runtime setting per active Task source, including the normalized Calendar-name mapping, explicit default Calendar, and worker-required stable Notion property IDs. It fails closed on missing, malformed, cross-owner, duplicate-Calendar-name, or incomplete configuration. Runtime property lookup must use `propertyId` only; do not add mutable-name fallbacks.

### Request flow

```
Lambda trigger (SQS / EventBridge)
  └─ lambda_function.lambda_handler
       ├─ reject superseded `execution` payloads
       └─ src/main.main(uuid)
            ├─ generate_config(uuid)
            ├─ MappingDomainConfig → active source settings
            ├─ NotionToken + GoogleToken
            └─ for each source: NotionService + GoogleService → sync
```

### Sync logic (`src/sync/sync.py`)

The mapping-domain migration preserves the existing event-ID-based synchronization algorithm.

1. Fetch Notion tasks and Google Calendar events for the configured source/window.
2. Read the task's persisted `GCal Event Id` and configured Calendar value.
3. If a Notion task has no Google event ID, create the Google event and write the returned provider event ID back to Notion.
4. If a task is marked deleted, delete the matching Google event by its stored provider event ID and apply the existing Notion cleanup behavior.
5. If a task already has an event ID, compare Notion/Google timestamps and execute the existing update or Calendar-move behavior.
6. `GCal Sync Time` remains part of timestamp reconciliation.
7. The existing Google → Notion path and force modes remain available.
8. Multiple Task sources are handled by invoking the same sync implementation once per current-contract source setting.

Do not introduce deterministic provider event identity, provider ownership metadata, or a new sync direction as part of this configuration migration.

### DynamoDB tables

Runtime tables (set via env vars):

- `DYNAMODB_MAPPING_DOMAIN_TABLE` — sole sync-configuration authority; owner partition plus `SourceMappingsIndex`
- `DYNAMODB_USER_TABLE` — sync-log summary only; never configuration
- `DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE` — Google OAuth tokens (refreshed in-place)
- `DYNAMODB_NOTION_OAUTH_TOKEN_TABLE` — Notion API token (encrypted as `enc:v1:…`)
- `DYNAMODB_SYNC_LOGS_TABLE` — sync result logs with TTL

The worker consumes normalized mapping-domain records and uses persisted provider property IDs directly. It does not fall back to mutable Notion property names or legacy configuration shapes. `GCal Event Id` / `GCal Sync Time` semantics remain unchanged. Distinct Task sources may share a Google Calendar; configuration identity does not redefine provider event identity.

### Token encryption

Notion and Google OAuth tokens may use `src/utils/token_crypto.py`. The `enc:v1:` prefix signals an encrypted value; in cloud mode the crypto key comes from SSM (`TOKEN_ENCRYPTION_KEY_SSM_PATH`), while local mode can read `TOKEN_ENCRYPTION_KEY`.

## Deployment

- **`dev` push** → auto-deploy to `dev-fn-notion-sync-gcal` Lambda via `.github/workflows/deploy-dev-lambda.yml`
- **`master` push** → semantic release only (git tag + GitHub Release), no Lambda deploy
- **Production** → manual `workflow_dispatch` only, workflow currently disabled in `.github/workflows/disabled/`

CI validates with `uv sync --frozen --dev`, Black, Flake8, unittest, secret scan, and workflow guardrails before any image build or Lambda update.

**Safety invariant**: `master` push must never build an ECR image or update Lambda. Only immutable image tags (`vX.Y.Z`, `sha-<short_sha>`) are allowed in production deploys.
