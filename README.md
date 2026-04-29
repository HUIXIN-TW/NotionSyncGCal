# Notion Task Two-Way Synchronise with Google Calendar Event

![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Lambda](https://img.shields.io/badge/Serverless-AWS%20Lambda-orange)

> AWS Lambda container that syncs Notion Task databases with Google Calendar events, running serverless with DynamoDB token storage.

Do you find yourself juggling between Notion and Google Calendar to manage your events? Fret not! This awesome code is here to save your day. It magically extracts event details from your Notion Database and seamlessly integrates them into your Google Calendar events. There's more! It even adds a handy URL to your GCal event, so you can effortlessly jump back to the specific Notion Page related to the event. How cool is that?

**Warning**: Proceed with caution! This repo wields the power to make changes to your Notion database and Google Calendar. So, if you're not confident about what you're doing, buckle up and brace yourself for some unexpected surprises.

🆕 [View Release v3.0.0 →](https://github.com/HUIXIN-TW/NotionSyncGCal/releases)

## Release v3.0.0 – DynamoDB Serverless Edition

- Breaking change: serverless storage now uses DynamoDB tables (tokens, user config, sync logs) instead of S3 objects.
- Lambda reads/writes by `uuid` (SQS/EventBridge payload) and persists refreshed tokens plus sync summaries into DynamoDB.
- Dev auto-deploy via GitHub Actions remains; production image publishing and production Lambda deployment are deferred until production infrastructure and IAM are ready.
- Release versions are tracked by Git tag and GitHub Release; `pyproject.toml` may stay static while this remains a Lambda app. See [doc/deployment.md](doc/deployment.md).
- Migration tip: seed the DynamoDB tables with your existing credentials/config and update environment variables to the new `DYNAMODB_*` names.

## What You Will Need to Get Started

- Google account
- Notion account
- Python 3.11+
- GitHub account (optional)
- AWS account and DynamoDB tables (for serverless/Lambda mode)

## Current Capabilities

- Update from Google Calendar to Notion task
- Update from Notion task to Google Calendar
- Automatically deletes GCal events when marked as deleted in Notion
- Timezone and date range customization in `notion_setting.json`
- Sync across _multiple calendars_ and choose which calendar you would like to sync by changing `gcal_dic` in `notion_setting.json`
- Custom Notion column names
- Google Calendar OAuth integration
- DynamoDB + Lambda integration for serverless execution

## Functions You Can Configure

- Ability to change timezones by changing `timecode` and `timezone` in `notion_setting`
- Ability to change the date range by changing `goback_days` and `goforward_days` in `notion_setting.json` (If you are new here, please use 1 and 2 days respectively before you understand the code)
- Able to decide the default length of new GCal events by changing `default_event_length` in `notion_setting.json`
- Option to delete GCal events if checked off as `GCal Deleted?` column in Notion
- Sync across _multiple calendars_ and choose which calendar you would like to sync by changing `gcal_dic` in `notion_setting.json`
- Able to name the required Notion columns whatever you want and have the code work by changing `page_property` in `notion_setting.json`
- Credential and OAuth consent screen with Google Calendar scope

## Project Structure

```
.
├── assets/                    # Images referenced by this README
├── doc/
│   └── deployment.md          # CI/CD workflow and deployment details
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
│   ├── config/config.py       # Local vs serverless mode config
│   ├── gcal/                  # Google Calendar service + OAuth token handling
│   ├── notion/                # Notion service + config + token handling
│   ├── sync/sync.py           # Bidirectional sync logic
│   ├── user_setting/          # Local notion_setting.json updater
│   └── utils/                 # Logging, DynamoDB, HTTP, crypto helpers
├── test/
│   └── test_token_crypto.py   # Unit tests for token encryption
├── token/                     # Local credentials (gitignored — never commit)
│   ├── client_secret.json     # Google OAuth client secret
│   ├── notion_setting.json    # Notion config + encrypted token
│   └── token.json             # Google OAuth token
└── token_template/            # Safe blank templates for token/ setup
    ├── notion_setting.json
    └── token.json
```

## Local Setup

```bash
git clone https://github.com/HUIXIN-TW/NotionSyncGCal.git
cd NotionSyncGCal

# Install dependencies (requires uv: https://docs.astral.sh/uv/getting-started/installation/)
uv sync
```

Configure Notion and Google Calendar:

- Duplicate the [Notion Template](https://huixin.notion.site/aa639e48cfee4216976756f33cf57c8e?v=6db9353f3bc54029807c539ffc3dfdb4).
- Set up a Notion integration and connect it to your database.
- Enable the Google Calendar API and download the `client_secret.json` file.
- Copy `token_template/notion_setting.json` → `token/notion_setting.json` and fill in your values.
- Copy `token_template/token.json` → `token/token.json` and complete the OAuth flow.

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

### Lambda Entrypoint

`lambda_function.py` is the Docker `CMD` entrypoint. It dispatches incoming events:

- **SQS**: reads `uuid` from `Records[].body`, calls `src/main.main(uuid)` per record.
- **EventBridge**: reads `uuid` from the event detail, calls `src/main.main(uuid)`.
- **API**: placeholder for future test-connection use.

### Environment Variables

Set the following variables in your Lambda configuration or `.env` file:

```bash
export APP_REGION=''
export DYNAMODB_USER_TABLE=''
export DYNAMODB_SYNC_LOGS_TABLE=''
export DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE=''
export DYNAMODB_NOTION_OAUTH_TOKEN_TABLE=''
```

Note: When using Lambda, no CLI arguments are passed. You must configure your `notion_config.json` values (e.g., `goback_days`, `goforward_days`) to control the sync range.

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

Deployment is handled by GitHub Actions workflows. See [doc/deployment.md](doc/deployment.md) for full details.

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

### Local Lambda Test

Run the local mock Lambda handler:

```bash
uv run python lambda_function.py
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

The `token/` directory is gitignored and must **never** be committed. It holds:

- `token/client_secret.json` — Google OAuth client credentials (download from Google Cloud Console)
- `token/notion_setting.json` — Notion API token (encrypted as `enc:v1:…`) + sync configuration
- `token/token.json` — Google OAuth access/refresh token (written by the OAuth flow)

Use `token_template/` as a reference for the expected JSON shape. In serverless mode (Lambda), all credentials are stored in DynamoDB and loaded by UUID — the `token/` directory is not used at runtime.

## Tips for First-Time Users

- Start with a small date range:

  ```json
  "goback_days": 1,
  "goforward_days": 2
  ```

- Test the tool locally before deploying to Lambda.
- Use the provided Notion template to avoid configuration issues.

Happy syncing! ✨
