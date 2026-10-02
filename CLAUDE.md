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

- **Local** (`APP_MODE=local`): loads the current mapping-domain document from `config/local.mapping-domain.json`; secrets are loaded from environment variables.
- **Cloud** (`APP_MODE=cloud`): requires a UUID, reads settings/Task sources/Calendar mappings from the mapping-domain table, and reads OAuth tokens from their UUID-keyed tables.

Do not infer mode from UUID. Do not fallback to `token/*.json`. Do not commit secrets.

Local configuration/credentials live in `.env.local`: `NOTION_TOKEN`, `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, and `GOOGLE_CALENDAR_REFRESH_TOKEN`. Cloud reuses the non-secret `GOOGLE_CALENDAR_CLIENT_ID`, loads OAuth tokens from DynamoDB, and resolves secrets through `GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH` and `TOKEN_ENCRYPTION_KEY_SSM_PATH`.

Tokens may be plaintext or `enc:v1:` encrypted. Use `src/utils/token_crypto.py:decrypt_token_if_encrypted()` at token read boundaries; `decrypt_token()` stays strict. In cloud mode, token encryption keys are resolved from SSM via `TOKEN_ENCRYPTION_KEY_SSM_PATH`; local mode may still use plaintext `TOKEN_ENCRYPTION_KEY`.

`MappingDomainConfig` is the only configuration boundary. It returns one current-contract runtime setting per active Task source, including the normalized Calendar-name mapping, explicit default Calendar, and worker-required stable Notion property IDs. It fails closed on missing, malformed, cross-owner, duplicate-Calendar-name, or incomplete configuration. Runtime property lookup must use `propertyId` only; do not add mutable-name fallbacks. `timeZone` is the temporal source of truth; `timeCode` remains current-contract metadata and must not drive date-specific runtime offsets.

### Request flow

```
Lambda trigger
  └─ lambda_function.lambda_handler
       ├─ SQS: parse JSON body object and require a non-empty `uuid`
       ├─ EventBridge: require detail object with a non-empty `uuid`
       └─ src/main.main(uuid)
            ├─ generate_config(uuid)
            ├─ MappingDomainConfig → active source settings
            ├─ NotionToken + GoogleToken
            └─ for each source: NotionService + GoogleService → sync
```

### Sync logic (`src/sync/sync.py`)

The worker uses deterministic provider identity for Notion-owned tasks:

1. Fetch Notion tasks and Google Calendar events for the configured source/window.
2. Derive each managed Google event ID from the stable Task Source `sourceId` plus immutable Notion page ID using versioned length-prefixed byte framing and a one-way digest.
3. Create supplies that deterministic ID to Google at insert time; update/delete/move resolve the same ID without reading Notion mirror state.
4. Google private extended properties contain only source ID, mapping ID, and mapping version for routing/reconciliation.
5. Calendar Mapping ID is not part of provider identity, so moving a task between configured Calendar mappings preserves the Google event ID while refreshing destination metadata.
6. The mapping/source/version stale-write fence is revalidated immediately before every Google provider mutation.
7. `GCal Sync Time` remains part of timestamp reconciliation.
8. Unmatched Google events are not materialized into Notion because Notion is authoritative task state and those events have no deterministic Notica task identity.
9. Multiple Task sources are handled by invoking the same sync implementation once per current-contract source setting.

### DynamoDB tables

Runtime tables (set via env vars):

- `DYNAMODB_MAPPING_DOMAIN_TABLE` — sole sync-configuration authority; owner partition plus `SourceMappingsIndex`
- `DYNAMODB_USER_TABLE` — sync-log summary only; never configuration
- `DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE` — Google OAuth tokens (refreshed in-place)
- `DYNAMODB_NOTION_OAUTH_TOKEN_TABLE` — Notion API token (encrypted as `enc:v1:…`)
- `DYNAMODB_SYNC_LOGS_TABLE` — sync result logs with TTL

The worker consumes only the current mapping-domain configuration shape and uses persisted provider property IDs directly. It does not fall back to mutable Notion property names. The legacy provider-event mirror is not runtime state or a configuration requirement; `GCal Sync Time` remains timestamp-reconciliation state. Distinct Task sources may share a Google Calendar; provider identity is derived from source + Notion page identity and intentionally excludes Calendar Mapping identity.

### Token encryption

Notion and Google OAuth tokens may use `src/utils/token_crypto.py`. The `enc:v1:` prefix signals an encrypted value; in cloud mode the crypto key comes from SSM (`TOKEN_ENCRYPTION_KEY_SSM_PATH`), while local mode can read `TOKEN_ENCRYPTION_KEY`.

## Deployment

- **`dev` push** → auto-deploy to `dev-fn-notion-sync-gcal` Lambda via `.github/workflows/deploy-dev-lambda.yml`
- **`master` push** → semantic release only (git tag + GitHub Release), no Lambda deploy
- **Production** → manual `workflow_dispatch` only, workflow currently disabled in `.github/workflows/disabled/`

CI validates with `uv sync --frozen --dev`, Black, Flake8, unittest, secret scan, and workflow guardrails before any image build or Lambda update.

**Safety invariant**: `master` push must never build an ECR image or update Lambda. Only immutable image tags (`vX.Y.Z`, `sha-<short_sha>`) are allowed in production deploys.
