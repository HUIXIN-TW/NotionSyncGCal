# Notion Task Two-Way Synchronise with Google Calendar Event

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Lambda](https://img.shields.io/badge/Serverless-AWS%20Lambda-orange)
![Deploy Status](https://github.com/HUIXIN-TW/NotionSyncGCal/actions/workflows/deploy_lambda.yml/badge.svg)

> Command-line interface to sync data between Notion Task and Google Calendar Event.

Do you find yourself juggling between Notion and Google Calendar to manage your events? Fret not! This awesome code is here to save your day. It magically extracts event details from your Notion Database and seamlessly integrates them into your Google Calendar events. There's more! It even adds a handy URL to your GCal event, so you can effortlessly jump back to the specific Notion Page related to the event. How cool is that?

**Warning**: Proceed with caution! This repo wields the power to make changes to your Notion database and Google Calendar. So, if you're not confident about what you're doing, buckle up and brace yourself for some unexpected surprises.

🆕 [View Release v2.0.0 →](https://github.com/HUIXIN-TW/NotionSyncGCal/releases)

## What You Will Need to Get Started

- Google account
- Notion account
- Python 3.8+
- GitHub account (optional)
- AWS account (for serverless mode)

## Current Capabilities

- Update from Google Calendar to Notion task
- Update from Notion task to Google Calendar
- Automatically deletes GCal events when marked as deleted in Notion
- Timezone and date range customization in `notion_setting.json`
- Sync across _multiple calendars_ and choose which calendar you would like to sync by changing `gcal_dic` in `notion_setting.json`
- Custom Notion column names
- Google Calendar OAuth integration
- S3 and Lambda integration for serverless execution

## Functions You Can Configure

- Ability to change timezones by changing `timecode` and `timezone` in `notion_setting`
- Ability to change the date range by changing `goback_days` and `goforward_days` in `notion_setting.json` (If you are new here, please use 1 and 2 days respectively before you understand the code)
- Able to decide the default length of new GCal events by changing `default_event_length` in `notion_setting.json`
- Option to delete GCal events if checked off as `GCal Deleted?` column in Notion
- Sync across _multiple calendars_ and choose which calendar you would like to sync by changing `gcal_dic` in `notion_setting.json`
- Able to name the required Notion columns whatever you want and have the code work by changing `page_property` in `notion_setting.json`
- Credential and OAuth consent screen with Google Calendar scope

## Local Usage

Go to the terminal and run the following commands:

```bash
git clone https://github.com/HUIXIN-TW/NotionSyncGCal.git
cd NotionSyncGCal
pip install -r requirements.txt
python3 src/main.py
```

Configure Notion and Google Calendar

- Duplicate the [Notion Template](https://huixin.notion.site/aa639e48cfee4216976756f33cf57c8e?v=6db9353f3bc54029807c539ffc3dfdb4).
- Set up a Notion integration and connect it to your database.
- Enable the Google Calendar API and download the `client_secret.json` file.
- Complete the `notion_setting.json` file in the `token` folder.

You found the above topic is unfamiliar? No worries! Just follow the [Beginner Guide](doc/beginner_guide.md) to set up your Notion and Google Calendar integration.

### Basic Synchronization

To run the basic synchronization between Notion and Google Calendar:

```bash
python3 src/main.py
```

### Synchronization with Specific Date Range

To synchronize events based on a specific date range, use the following command:

```bash
python3 src/main.py -t <look_back_days> <look_ahead_days>
```

`<look_back_days>`: Number of days to look back from the current date.

`<look_ahead_days>`: Number of days to look forward from the current date.

### Force Sync Options

#### Sync from Google Calendar to Notion

To force an update of Notion tasks from Google Calendar events within a specified date range, use the following command:

```bash
python3 src/main.py -g <look_back_days> <look_ahead_days>
```

#### Sync from Notion to Google Calendar

To force an update of Google Calendar events from Notion tasks within a specified date range, use the following command:

```bash
python3 src/main.py -n <look_back_days> <look_ahead_days>
```

## AWS Lambda Integration

### How It Works

- Stores `xxx.json` in S3.
- Lambda reads these files at runtime using environment variables.
- Automatically refreshes expired tokens and saves them back to S3.

### Environment Variables

Set the following variables in your Lambda configuration or `.env` file:

```bash
export S3_BUCKET_NAME='your-bucket-name'
export S3_GOOGLE_TOKEN_PATH='<foldername>/token.json'
export S3_NOTION_TOKEN_PATH='<foldername>/notion_token.json'
export S3_NOTION_CONFIG_PATH='<foldername>/notion_config.json'
```

Note: When using Lambda, no CLI arguments are passed. You must configure your `notion_config.json` values (e.g., `goback_days`, `goforward_days`) to control the sync range.

### IAM Permissions Required for Lambda Role

```json
{
  "Effect": "Allow",
  "Action": ["s3:GetObject", "s3:PutObject"],
  "Resource": "arn:aws:s3:::your-bucket-name/your-folder/*"
}
```

### Deploying to Lambda

Use GitHub Actions:

- Create a GitHub Action to build and deploy your Lambda function.
- Use the provided `lambda-ecr-deploy.yml` file in the `.github/workflows` directory.

## Testing and Monitoring

### Local Testing

Run the local mock Lambda handler:

```bash
python lambda_function.py
```

You should see log output from both Notion and Google token readers, calendar events fetched, and sync logs.

### Monitoring with AWS CloudWatch

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

## Tips for First-Time Users

- Start with a small date range:
  ```json
  "goback_days": 1,
  "goforward_days": 2
  ```
- Test the tool locally before deploying to Lambda.
- Use the provided Notion template to avoid configuration issues.

Happy syncing! ✨
