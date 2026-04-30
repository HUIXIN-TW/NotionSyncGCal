# Notion Task Two-Way Synchronise with Google Calendar Event

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Lambda](https://img.shields.io/badge/AWS%20Lambda-DynamoDB-orange)

> AWS Lambda container and local developer runner that sync Notion Task databases with Google Calendar events.

Do you find yourself juggling between Notion and Google Calendar to manage your events? Fret not! This awesome code is here to save your day. It magically extracts event details from your Notion Database and seamlessly integrates them into your Google Calendar events. There's more! It even adds a handy URL to your GCal event, so you can effortlessly jump back to the specific Notion Page related to the event. How cool is that?

**Warning**: Proceed with caution! This repo wields the power to make changes to your Notion database and Google Calendar. So, if you're not confident about what you're doing, buckle up and brace yourself for some unexpected surprises.

🆕 [View Release v3.0.0 →](https://github.com/HUIXIN-TW/NotionSyncGCal/releases)

## Release v3.0.0 – DynamoDB Cloud Edition

- Breaking change: cloud storage now uses DynamoDB tables (tokens, user config, sync logs) instead of S3 objects.
- Lambda reads/writes by `uuid` (SQS/EventBridge payload) and persists refreshed tokens plus sync summaries into DynamoDB.
- Dev auto-deploy via GitHub Actions remains; production image publishing and production Lambda deployment are deferred until production infrastructure and IAM are ready.
- Release versions are tracked by Git tag and GitHub Release; `pyproject.toml` may stay static while this remains a Lambda app. See [docs/deployment.md](docs/deployment.md).
- Migration tip: seed the DynamoDB tables with your existing credentials/config and update environment variables to the new `DYNAMODB_*` names.

## What You Will Need to Get Started

- Google account
- Notion account
- Python 3.11+
- GitHub account (optional)
- AWS account and DynamoDB tables (for cloud/Lambda mode)

## Current Capabilities

- Update from Google Calendar to Notion task
- Update from Notion task to Google Calendar
- Automatically deletes GCal events when marked as deleted in Notion
- Timezone and date range customization in `config/local.notion-setting.json` or cloud user config
- Sync across _multiple calendars_ by changing `gcal_dic` in local config or cloud user config
- Custom Notion column names
- Google Calendar OAuth integration
- DynamoDB + Lambda integration for cloud execution

## Functions You Can Configure

- Ability to change timezones by changing `timecode` and `timezone`
- Ability to change the date range by changing `goback_days` and `goforward_days`
- Able to decide the default length of new GCal events by changing `default_event_length`
- Option to delete GCal events if checked off as `GCal Deleted?` column in Notion
- Sync across _multiple calendars_ and choose which calendar you would like to sync by changing `gcal_dic`
- Able to name the required Notion columns whatever you want and have the code work by changing `page_property`
- Credential and OAuth consent screen with Google Calendar scope

## Project Structure

```
.
├── assets/                    # Images referenced by this README
├── docs/
│   ├── deployment.md          # CI/CD workflow and deployment details
│   └── local-dev-sync-runner.md  # Detailed local/cloud runbook
├── Dockerfile                 # Lambda container image definition
├── lambda_function.py         # Lambda handler (entrypoint)
├── pyproject.toml             # Project metadata and runtime dependencies
├── uv.lock                    # Locked dependency tree
├── makefile                   # Lint shortcuts
├── scripts/
│   ├── check_lambda_deploy_workflows.sh   # CI guardrail: Lambda deploy rules
│   └── check_no_plaintext_secrets.sh      # CI guardrail: secret scanning
├── src/
│   ├── main.py                # Core sync logic, CLI entrypoint
│   ├── config/config.py       # APP_MODE cloud/local config branch
│   ├── gcal/                  # Google Calendar service + OAuth token handling
│   ├── notion/                # Notion service + config + token handling
│   ├── sync/sync.py           # Bidirectional sync logic
│   ├── user_setting/          # Date-range update helpers
│   └── utils/                 # Logging, DynamoDB, HTTP, crypto helpers
├── test/
│   └── test_token_crypto.py   # Unit tests for token encryption
├── config/
│   └── local.notion-setting.example.json  # Safe local config template
└── .env.local.example        # Safe local env template
```

## Setup

```bash
git clone https://github.com/HUIXIN-TW/NotionSyncGCal.git
cd NotionSyncGCal

# Install dependencies (requires uv: https://docs.astral.sh/uv/getting-started/installation/)
uv sync
```

Run tests:

```bash
uv run python -m unittest discover test/ -v
```

## Runtime Modes

Runtime mode is explicit. Set `APP_MODE` instead of inferring behavior from whether a UUID exists.

- `APP_MODE=local`: no AWS required. `NOTION_TOKEN` and Google OAuth credentials are loaded from `.env.local`; Notion database/calendar/property config is loaded from `config/local.notion-setting.json`.
- `APP_MODE=cloud`: UUID required. Config and tokens are loaded from DynamoDB tables keyed by `uuid`.

Tokens may be plaintext or `enc:v1:` encrypted. Encrypted tokens require `TOKEN_ENCRYPTION_KEY` to match the key used to encrypt them. The old `token/` path is deprecated and is not the runtime path anymore.

## Local Setup

Configure Notion and Google Calendar:

- Duplicate the [Notion Template](https://huixin.notion.site/aa639e48cfee4216976756f33cf57c8e?v=6db9353f3bc54029807c539ffc3dfdb4).
- Set up a Notion integration and connect it to your database.
- Enable the Google Calendar API and create OAuth credentials.
- Create local files from the safe examples:

  ```bash
  cp .env.local.example .env.local
  cp config/local.notion-setting.example.json config/local.notion-setting.json
  ```

- Fill `.env.local` with `APP_MODE=local`, `NOTION_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN`. Optional `GOOGLE_TOKEN_URI` and `GOOGLE_SCOPES` can override defaults.
- Fill `config/local.notion-setting.json` with your Notion database ID, calendar mapping (`gcal_dic`), and Notion page property mapping (`page_property`).

For detailed local and cloud runner usage, see [docs/local-dev-sync-runner.md](docs/local-dev-sync-runner.md).

### Basic Synchronization

```bash
uv run python src/main.py
```

### Synchronization with Specific Date Range

```bash
uv run python src/main.py -t <look_back_days> <look_ahead_days>
```

`<look_back_days>`: Number of days to look back from the current date.

`<look_ahead_days>`: Number of days to look forward from the current date.

### Force Sync Options

#### Sync from Google Calendar to Notion

```bash
uv run python src/main.py -g <look_back_days> <look_ahead_days>
```

#### Sync from Notion to Google Calendar

```bash
uv run python src/main.py -n <look_back_days> <look_ahead_days>
```

## AWS Lambda Integration

### How It Works

- Stores user config and OAuth tokens in DynamoDB tables keyed by `uuid`.
- Lambda reads config/tokens at runtime using the `uuid` provided by your trigger payload (for example, an SQS message body).
- Token refreshes and sync summaries are written back to DynamoDB (including the sync log table with TTL).
- Lambda must run with `APP_MODE=cloud`.

### Lambda Entrypoint

`lambda_function.py` is the Docker `CMD` entrypoint. It dispatches incoming events:

- **SQS**: reads `uuid` from `Records[].body`, calls `src/main.main(uuid)` per record.
- **EventBridge**: reads `uuid` from the event detail, calls `src/main.main(uuid)`.
- **API**: placeholder for future test-connection use.

### Environment Variables

Set the following variables in your Lambda configuration or `.env` file:

```bash
export APP_MODE='cloud'
export APP_STAGE='dev'
export APP_REGION=''
export AWS_REGION=''
export DYNAMODB_USER_TABLE=''
export DYNAMODB_SYNC_LOGS_TABLE=''
export DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE=''
export DYNAMODB_NOTION_OAUTH_TOKEN_TABLE=''
export GOOGLE_CALENDAR_CLIENT_ID=''
export GOOGLE_CALENDAR_CLIENT_SECRET=''
export TOKEN_ENCRYPTION_KEY=''  # required when DynamoDB tokens use enc:v1: encryption
```

Cloud Lambda does not use local-mode variables such as `NOTION_TOKEN`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, or `GOOGLE_REFRESH_TOKEN`. It loads user config and tokens from DynamoDB by UUID. Note: When using Lambda, no CLI arguments are passed. Configure user config values such as `goback_days` and `goforward_days` in DynamoDB.

### IAM Permissions Required for Lambda Role

```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:PutItem"],
  "Resource": [
    "arn:aws:dynamodb:<region>:<account-id>:table/<DYNAMODB_USER_TABLE>",
    "arn:aws:dynamodb:<region>:<account-id>:table/<DYNAMODB_SYNC_LOGS_TABLE>",
    "arn:aws:dynamodb:<region>:<account-id>:table/<DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE>",
    "arn:aws:dynamodb:<region>:<account-id>:table/<DYNAMODB_NOTION_OAUTH_TOKEN_TABLE>"
  ]
}
```

### Deploying to Lambda

Deployment is handled by GitHub Actions workflows. See [docs/deployment.md](docs/deployment.md) for full details.

Current workflow split:

- Dev push -> `.github/workflows/deploy-dev-lambda.yml` -> build/push dev image -> deploy dev Lambda.
- Master push -> `.github/workflows/release-semantic.yml` -> semantic-release only.
- Production image publish -> deferred until production infrastructure, IAM, and cross-account ECR access are ready.
- Production Lambda deploy -> `.github/workflows/disabled/deploy-prd-lambda.yml`, disabled until production infrastructure and IAM are ready.

## Testing

### Run Unit Tests

```bash
uv run python -m pytest test/
```

Or using the standard library runner:

```bash
uv run python -m unittest discover test/
```

### Local Cloud Runner

Run local code with dev AWS-backed config by UUID:

```bash
./scripts/local-run-dev-sync.sh --mode cloud --uuid <uuid>
```

You should see log output from both Notion and Google token readers, calendar events fetched, and sync logs.

### Sync Response Payload

A successful sync always returns `statusCode: 200`. Per-task errors are collected and returned in the `errors` list rather than stopping the entire sync.

```json
{
  "statusCode": 200,
  "body": {
    "status": "sync_success",
    "message": {
      "summary": { "google_event_count": 5, "notion_task_count": 5 },
      "trigger_time": "2024-01-01T00:00:00.000Z",
      "errors": [
        {
          "notion_task_id": "page-uuid-1",
          "notion_task_name": "Weekly Sync Meeting",
          "gcal_event_id": "gcal-event-id-1",
          "gcal_event_title": "Weekly Sync Meeting",
          "action": "update_gcal",
          "error": "APIResponseError: ..."
        },
        {
          "notion_task_id": null,
          "notion_task_name": null,
          "gcal_event_id": "gcal-event-id-2",
          "gcal_event_title": "Team Standup",
          "action": "create_notion",
          "error": "Skipped: GCal event description exceeds Notion's 2000-character rich_text limit (4469 chars). Syncing this event would corrupt data integrity."
        }
      ]
    }
  }
}
```

**`action` values:**

| Value           | Description                                                         |
| --------------- | ------------------------------------------------------------------- |
| `create_gcal`   | Creating a new GCal event from a Notion task                        |
| `delete_gcal`   | Deleting a GCal event (and Notion task) from a Notion deletion flag |
| `update_gcal`   | Updating GCal event because Notion task is newer                    |
| `update_notion` | Updating Notion task because GCal event is newer                    |
| `create_notion` | Creating a new Notion task from a GCal event                        |

`notion_task_id` and `notion_task_name` are `null` for `create_notion` actions (no Notion page exists yet).
`gcal_event_id` and `gcal_event_title` are `null` for `create_gcal` actions (no GCal event exists yet).

## Monitoring with AWS CloudWatch

View logs in CloudWatch:

```bash
aws logs describe-log-streams \
  --log-group-name /aws/lambda/<lambda-function-name> \
  --order-by LastEventTime \
  --descending \
  --limit 1

aws logs get-log-events \
  --log-group-name /aws/lambda/<lambda-function-name> \
  --log-stream-name <log-stream-name>
```

### Setting Up CloudWatch Alarms

To monitor your Lambda function effectively, you can set up CloudWatch alarms to notify you of any issues or performance metrics that exceed your thresholds.

1. Go to the CloudWatch console.
2. Select "Alarms" from the left navigation pane.
3. Click on "Create Alarm".
4. Choose the metric you want to monitor (e.g., "Errors", "Duration").
5. Set the conditions for the alarm.
6. Configure actions to notify you (e.g., via SNS).
7. Review and create the alarm.

![alt text](/assets/cloudwatch_alarms.png)

### Setting Up CloudWatch Dashboard

To visualize your Lambda function's performance, you can create a CloudWatch dashboard:

1. Go to the CloudWatch console.
2. Select "Dashboards" from the left navigation pane.
3. Click on "Create dashboard".
4. Choose a name for your dashboard.
5. Add widgets to visualize metrics like "Invocations", "Errors", "Duration", etc.
6. Customize the layout and save the dashboard.

![alt text](/assets/cloudwatch_dashboard.png)

## Cost-Effective Setup

This prevents your function from being invoked in parallel, and guarantees:

- Only one sync runs at a time
- Any overlapping triggers will be throttled instead of stacking

```bash
aws lambda put-function-concurrency \
  --function-name notion-sync-gcal \
  --reserved-concurrent-executions 1
```

By default, CloudWatch keeps logs forever = `$$$` long-term. Set a retention policy to keep logs for 7 days.

```bash
aws logs put-retention-policy \
  --log-group-name /aws/lambda/notion-sync-gcal \
  --retention-in-days 7
```

## Secrets and Config Handling

Local mode uses:

- `.env.local` for `NOTION_TOKEN` and Google OAuth env vars.
- `config/local.notion-setting.json` for Notion database, calendar, date range, and page property mapping.

Cloud mode uses DynamoDB by UUID for config and tokens. Plaintext and `enc:v1:` encrypted tokens are supported; encrypted tokens require the matching `TOKEN_ENCRYPTION_KEY`. The `token/` directory is deprecated, gitignored, and must not be reintroduced as a runtime path.

## Tips for First-Time Users

- Start with a small date range:

  ```json
  "goback_days": 1,
  "goforward_days": 2
  ```

- Test the tool locally before deploying to Lambda.
- Use the provided Notion template to avoid configuration issues.

Happy syncing! ✨
