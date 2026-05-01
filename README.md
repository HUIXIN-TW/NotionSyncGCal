# NotionSyncGCal Lambda

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Lambda](https://img.shields.io/badge/AWS%20Lambda-Container-orange)

AWS Lambda container and local developer runner for synchronizing Notion task databases with Google Calendar events.

This tool mutates both Notion and Google Calendar data. Validate configuration and run against test data first.

Releases: https://github.com/HUIXIN-TW/NotionSyncGCal/releases

## What It Does

- Bidirectional sync between Notion tasks and Google Calendar events.
- Supports multiple Google calendars via `gcal_dic`.
- Supports custom Notion property mapping via `page_property`.
- Supports force-sync modes via CLI (`-g`, `-n`).
- Handles cancelled Google Calendar events during sync filtering.
- Expands recurring Google Calendar events and uses each expanded event instance ID for matching/sync.
- Persists cloud sync logs in DynamoDB.

## Sync Behavior

- A Notion task without a linked GCal event ID creates a Google Calendar event.
- An unmatched Google Calendar event creates a Notion task.
- Matched Notion/GCal records are updated based on last-modified timestamps.
- A Notion deletion flag deletes the linked Google Calendar event and the Notion task.
- CLI date flags are runtime in-memory overrides only and do not rewrite local JSON config.

## Current Architecture

The runtime uses an explicit mode switch via `APP_MODE`:

- `APP_MODE=local`: uses `.env.local` secrets and `config/local.notion-setting.json` for local development.
- `APP_MODE=cloud`: uses DynamoDB records keyed by `uuid` and resolves cloud secrets from SSM SecureString paths at runtime.

Current cloud/runtime notes:

- Cloud secret values are resolved via:
  - `GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH`
  - `TOKEN_ENCRYPTION_KEY_SSM_PATH`
- Cloud runtime should not use plaintext `GOOGLE_CALENDAR_CLIENT_SECRET` or plaintext `TOKEN_ENCRYPTION_KEY` env vars.
- Token JSON files under `token/` are not runtime inputs.
- Cloud token payloads at rest in DynamoDB should remain `enc:v1:` encrypted.

## Requirements

- Python `>=3.11` (from `pyproject.toml`)
- `uv`
- Notion account + Notion integration token
- Google account + OAuth client credentials
- AWS account only for `APP_MODE=cloud`

## Quick Setup

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run python -m unittest discover -s test -v
```

Run coverage:

```bash
uv run coverage run -m unittest discover -s test -v
uv run coverage report -m
```

Coverage enforcement is configured in `.coveragerc` (`fail_under = 50`).

## Runtime Modes

### `APP_MODE=local`

No AWS dependency for runtime.

- Secrets are read from `.env.local`:
  - `NOTION_TOKEN`
  - `GOOGLE_CLIENT_ID`
  - `GOOGLE_CLIENT_SECRET`
  - `GOOGLE_REFRESH_TOKEN`
  - `TOKEN_ENCRYPTION_KEY` only when local token values are stored as `enc:v1:` payloads
- Structured local sync config is read from:
  - `config/local.notion-setting.json`

### `APP_MODE=cloud`

Requires a `uuid` and AWS access.

- Loads user config and tokens from DynamoDB tables (UUID-keyed):
  - user config table
  - Google OAuth token table
  - Notion OAuth token table
  - sync logs table
- Lambda environment includes SSM parameter paths:
  - `GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH`
  - `TOKEN_ENCRYPTION_KEY_SSM_PATH`
- Runtime resolves SSM SecureString values with decryption.
- Runtime does not use plaintext `GOOGLE_CALENDAR_CLIENT_SECRET` or plaintext `TOKEN_ENCRYPTION_KEY` env vars.
- Runtime does not use local `token/*.json` files.

## Local Development

Create local files from examples:

```bash
cp .env.local.example .env.local
cp config/local.notion-setting.example.json config/local.notion-setting.json
```

Run sync locally with explicit mode:

```bash
APP_MODE=local uv run python src/main.py
APP_MODE=local uv run python src/main.py -t <goback_days> <goforward_days>
APP_MODE=local uv run python src/main.py -g <goback_days> <goforward_days>
APP_MODE=local uv run python src/main.py -n <goback_days> <goforward_days>
```

CLI date range flags (`-t`, `-g`, `-n`) are runtime in-memory overrides only. They do not modify `config/local.notion-setting.json`.

Generate a local `GOOGLE_REFRESH_TOKEN` with:

```bash
uv run python scripts/generate-google-refresh-token.py --client-id <client_id> --client-secret <client_secret>
```

Do not commit `.env.local`.

## Cloud Deployment

Required Lambda environment shape:

```bash
APP_MODE=cloud
APP_STAGE=dev
APP_REGION=ap-southeast-2
DYNAMODB_USER_TABLE=...
DYNAMODB_SYNC_LOGS_TABLE=...
DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE=...
DYNAMODB_NOTION_OAUTH_TOKEN_TABLE=...
GOOGLE_CALENDAR_CLIENT_ID=...
GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH=/dev/notica/google_calendar_client_secret
TOKEN_ENCRYPTION_KEY_SSM_PATH=/dev/notica/token_encryption_key
```

IAM for Lambda execution role should include least privilege:

- DynamoDB read/write permissions for exact tables and required indexes.
- SSM permissions:
  - `ssm:GetParameter` for runtime single-parameter secret resolution.
  - `ssm:GetParameters` only if batch secret lookup is introduced.
  - Permissions must be scoped to exact parameter ARNs.
- `kms:Decrypt` only if those SecureString parameters use a customer-managed KMS key.

Avoid wildcard permissions such as `ssm:*`.

Detailed deployment workflow behavior is documented in `docs/deployment.md`.

## Local Cloud Runner

Run local code with dev cloud configuration:

```bash
./scripts/local-run-dev-sync.sh --mode cloud --uuid <uuid>
```

Run local-only mode:

```bash
./scripts/local-run-dev-sync.sh --mode local
```

Notes:

- Cloud runner loads dev Lambda env configuration and resolves SSM values using your current AWS credentials.
- Local runner reads `.env.local`.
- Runner output is designed not to print sensitive secret values.

## Project Structure

```text
.
├── .coveragerc
├── .env.local.example
├── config/
│   └── local.notion-setting.example.json
├── docs/
│   ├── deployment.md
│   └── local-dev-sync-runner.md
├── lambda_function.py
├── pyproject.toml
├── scripts/
│   ├── generate-google-refresh-token.py
│   ├── local-run-dev-sync.sh
│   └── local_invoke_sync_lambda.py
├── src/
│   ├── config/config.py
│   ├── gcal/
│   ├── notion/
│   ├── sync/sync.py
│   └── utils/
│       ├── ssm_secrets.py
│       └── token_crypto.py
└── test/
```

## Security and Config Handling

- Local secrets (`.env.local`) are gitignored.
- `config/local.notion-setting.json` is gitignored.
- `token/` is deprecated and ignored.
- Cloud secret inputs are SSM path env vars, not plaintext secret env values.
- Cloud token payloads in DynamoDB should stay `enc:v1:` encrypted at rest.
- Do not log tokens or secret values.

## CI and Deployment Workflows

- Dev deploy: `.github/workflows/deploy-dev-lambda.yml`
  - Trigger: push to `dev`
  - Runs validation (format/lint/unit tests/coverage/secret checks/workflow guardrails) before deploy
  - Builds and pushes image, then updates dev Lambda
- Release: `.github/workflows/release-semantic.yml`
  - Trigger: push to `master`
  - Runs validation before semantic release
  - Creates Git tag and GitHub Release only
- Production Lambda deploy workflow exists under `.github/workflows/disabled/` and is currently disabled/manual.

## Further Documentation

- `docs/local-dev-sync-runner.md`: detailed local/cloud runner behavior and troubleshooting
- `docs/deployment.md`: CI/CD and environment-level deployment policy
