# Local Dev Sync Runner

## Purpose

`scripts/local-run-dev-sync.sh` runs the Notion-GCal sync from local source code with an explicit `APP_MODE`.

Use it to validate local changes without deploying first. The runner supports both AWS-backed dev data and fully local credentials/config. It does not write credentials to disk.

## Modes

### `cloud`

Cloud mode uses local code with dev AWS-backed config for one user UUID.

```bash
./scripts/local-run-dev-sync.sh --mode cloud --uuid xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The shell script validates AWS credentials, prints only safe identity details, loads the dev Lambda environment config, exports `APP_MODE=cloud`, and invokes the Python helper with `--uuid`.

### `local`

Local mode uses local env/config only and does not require AWS.

```bash
./scripts/local-run-dev-sync.sh --mode local
```

The shell script loads `.env.local`, validates `APP_MODE=local`, validates required local credentials, checks `config/local.notion-setting.json`, and invokes the Python helper without a UUID.

## Prerequisites

Required for both modes:

| Tool | Purpose |
|------|---------|
| `uv` | Runs the Python helper with project dependencies |
| `python3` | Python runtime |

Required for cloud mode only:

| Tool | Purpose |
|------|---------|
| `aws` CLI | Validates identity and reads dev Lambda environment variables |
| `jq` | Parses AWS CLI JSON |

Install dependencies:

```bash
uv sync
```

## Required Local Files

Local mode requires these untracked files:

```bash
.env.local
config/local.notion-setting.json
```

Create them from the examples:

```bash
cp .env.local.example .env.local
cp config/local.notion-setting.example.json config/local.notion-setting.json
```

Fill in `.env.local` with local-only secrets and keep `APP_MODE=local`:

```bash
APP_MODE=local
APP_STAGE=dev
APP_REGION=ap-southeast-2
AWS_REGION=ap-southeast-2
NOTION_TOKEN=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

`GOOGLE_TOKEN_URI` and `GOOGLE_SCOPES` are optional. If omitted, the runtime uses the Google OAuth token endpoint and the app's default calendar/profile scopes.

Fill `config/local.notion-setting.json` with your Notion database ID, calendar mapping (`gcal_dic`), and page property mapping (`page_property`).

## Generate Google Refresh Token

Local runtime reads Google credentials from `.env.local`. If you need a `GOOGLE_REFRESH_TOKEN`, use the standalone developer setup helper:

```bash
uv run python scripts/generate-google-refresh-token.py \
  --client-id your_google_desktop_client_id \
  --client-secret your_google_desktop_client_secret
```

The helper uses an in-memory OAuth client config and does not read or write token JSON files. Paste the printed env snippet into `.env.local`:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GOOGLE_TOKEN_URI=https://oauth2.googleapis.com/token
```

Do not commit `.env.local` or any generated env snippet. Refresh-token generation is separate from runtime sync.

## Encrypted Tokens

Local and cloud token values may be plaintext or `enc:v1:` encrypted:

- Plaintext `NOTION_TOKEN` and `GOOGLE_REFRESH_TOKEN` work without `TOKEN_ENCRYPTION_KEY`.
- Encrypted local tokens in `.env.local` require `TOKEN_ENCRYPTION_KEY` to match the key used to encrypt them.
- Cloud tokens loaded from DynamoDB can also be plaintext or `enc:v1:` encrypted.
- A decrypt failure means the key is missing, the key does not match, or the encrypted payload is malformed.

Do not print plaintext or encrypted token values in logs, docs, or shell output.

The canonical local config location is the repository root `config/` directory:

```bash
config/local.notion-setting.example.json
config/local.notion-setting.json
```

Do not put real local JSON config under `src/config/`; that directory is for Python config code only.

## Run Local Mode

```bash
./scripts/local-run-dev-sync.sh --mode local
```

Validation-only:

```bash
./scripts/local-run-dev-sync.sh --mode local --dry-run
```

Local mode validates:

- `.env.local` exists.
- `.env.local` sets `APP_MODE=local`.
- `NOTION_TOKEN` is set.
- `GOOGLE_CLIENT_ID` is set.
- `GOOGLE_CLIENT_SECRET` is set.
- `GOOGLE_REFRESH_TOKEN` is set.
- `config/local.notion-setting.json` exists.

The runner does not require or validate AWS credentials in local mode.

## Run Cloud Mode

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
export APP_REGION=ap-southeast-2

# Optional account guard:
export EXPECTED_AWS_ACCOUNT_ID=262835400669

./scripts/local-run-dev-sync.sh --mode cloud --uuid xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Validation-only:

```bash
./scripts/local-run-dev-sync.sh --mode cloud --uuid dummy-uuid --dry-run
```

Cloud mode validates:

- `AWS_ACCESS_KEY_ID` is set.
- `AWS_SECRET_ACCESS_KEY` is set.
- `AWS_SESSION_TOKEN` is set.
- One region variable is set: `APP_REGION`, or `AWS_REGION`.
- `aws sts get-caller-identity` succeeds.
- If `EXPECTED_AWS_ACCOUNT_ID` is set, the current AWS account matches it.
- `--uuid` is supplied.
- Required dev Lambda environment variables can be loaded.
- The dev Lambda environment includes `APP_MODE=cloud`.

The runner prints only safe AWS identity details:

- Account ID
- ARN
- Region

It never prints AWS secret keys, session tokens, Notion tokens, Google refresh tokens, or encryption keys.

## Required Cloud Env Vars

These must exist in the current shell before cloud mode runs:

| Variable | Required | Notes |
|----------|----------|-------|
| `AWS_ACCESS_KEY_ID` | Yes | Short-lived AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Yes | Secret access key, never printed |
| `AWS_SESSION_TOKEN` | Yes | Required for short-lived sessions |
| `APP_REGION` or `AWS_REGION` | Yes | AWS region |
| `EXPECTED_AWS_ACCOUNT_ID` | Optional | Refuses the run when the current account differs |

## Required Dev Lambda Env Var

The deployed dev Lambda must use the explicit cloud branch:

```bash
APP_MODE=cloud
```

The local cloud runner also exports `APP_MODE=cloud` before invoking the helper.

Cloud Lambda should not require local-mode variables such as `NOTION_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, or `GOOGLE_REFRESH_TOKEN`. It uses DynamoDB-backed config/tokens and cloud Google OAuth client env vars instead.
Cloud mode also requires:
- `GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH`
- `TOKEN_ENCRYPTION_KEY_SSM_PATH`
Cloud mode does not use plaintext `GOOGLE_CALENDAR_CLIENT_SECRET` or plaintext `TOKEN_ENCRYPTION_KEY`.

## Verify Ignored Local Files

The real local files must be ignored by git:

```bash
git check-ignore -v .env.local
git check-ignore -v config/local.notion-setting.json
git check-ignore -v token/token.json
```

The safe examples should not be ignored:

```bash
git check-ignore -v .env.local.example || true
git check-ignore -v config/local.notion-setting.example.json || true
```

## Helper Behavior

The shell runner delegates to:

```bash
uv run python scripts/local_invoke_sync_lambda.py --mode cloud --uuid <uuid>
uv run python scripts/local_invoke_sync_lambda.py --mode local
```

Cloud mode invokes the existing local Lambda path with an SQS-shaped event, preserving the dev UUID flow.

Local mode calls:

```python
src.main.main(uuid=None)
```

## Troubleshooting

### `APP_MODE` missing or wrong

Local mode requires `.env.local` to contain:

```bash
APP_MODE=local
```

Cloud mode exports `APP_MODE=cloud`. The dev Lambda environment should also set `APP_MODE=cloud`.

### `NOTION_TOKEN` missing

Local mode reads `NOTION_TOKEN` from `.env.local`. Add a local Notion internal integration token and rerun. The runner validates presence only and does not print the value.

### Google refresh token invalid

If sync fails with a Google refresh error, the local `GOOGLE_REFRESH_TOKEN` may be expired, revoked, or issued for a different OAuth client. Re-authorize locally and update `.env.local`.

### Encrypted token decrypt failure

If sync fails with `Failed to decrypt Notion token` or `Failed to decrypt encrypted Google OAuth token`, check:

- Local mode: `TOKEN_ENCRYPTION_KEY` is set when the token starts with `enc:v1:`.
- Cloud mode: `TOKEN_ENCRYPTION_KEY_SSM_PATH` points to a valid SecureString parameter.
- The key is the same 64-character hex key used to encrypt the token.
- The encrypted payload was copied without truncation or extra whitespace.

Plaintext tokens do not require `TOKEN_ENCRYPTION_KEY`.

### Local config JSON missing or malformed

Create the file if it is missing:

```bash
cp config/local.notion-setting.example.json config/local.notion-setting.json
```

If it exists but sync fails while loading Notion config, validate the JSON syntax and required database/property fields.

Make sure the file is in root `config/`, not `src/config/`.

### Wrong AWS account

Set `EXPECTED_AWS_ACCOUNT_ID` when running cloud mode:

```bash
export EXPECTED_AWS_ACCOUNT_ID=262835400669
```

If the current caller account differs, the runner exits before loading config or invoking sync.

### Expired AWS session token

If `aws sts get-caller-identity` fails, refresh credentials through SSO or by assuming the dev role again, then rerun:

```bash
aws sso login --profile dev
eval "$(aws configure export-credentials --profile dev --format env)"
```

### UUID missing in cloud mode

Cloud mode requires `--uuid`:

```bash
./scripts/local-run-dev-sync.sh --mode cloud --uuid xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

Local mode does not use UUID.

## Security

- Never commit `.env.local`.
- Never commit `config/local.notion-setting.json`.
- Never print secrets in shell scripts, docs, logs, or test fixtures.
- `token/` is deprecated and must not be reintroduced.
- Use short-lived AWS credentials for cloud mode.
- Prefer `EXPECTED_AWS_ACCOUNT_ID` in cloud mode to prevent accidental non-dev runs.
