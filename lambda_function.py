import json
from datetime import datetime, timezone
import pytz
from src.main import main as run_sync_notion_and_google


def lambda_handler(event, context):
    """
    AWS Lambda Handler to always run the CLI with -t 3 90 and include Perth timezone information.
    """
    try:
        # Get the current date, time, and timezone in UTC
        now_utc = datetime.now(timezone.utc)
        utc_date = now_utc.strftime("%Y-%m-%d")
        utc_time = now_utc.strftime("%H:%M:%S")
        utc_zone = now_utc.tzname()

        # Convert to Perth timezone
        perth_tz = pytz.timezone("Australia/Perth")
        now_perth = datetime.now(perth_tz)
        perth_date = now_perth.strftime("%Y-%m-%d")
        perth_time = now_perth.strftime("%H:%M:%S")
        perth_zone = now_perth.tzname()

        # Simulate the command-line arguments: -t 3 90
        cli_args = ["main.py", "-t", "3", "90"]
        run_sync_notion_and_google(cli_args)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "Sync completed",
                "utc_date": utc_date,
                "utc_time": utc_time,
                "utc_time_zone": utc_zone,
                "perth_date": perth_date,
                "perth_time": perth_time,
                "perth_time_zone": perth_zone,
            }),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e), "status": "Sync failed"}),
        }


# Mock event and context for local testing
if __name__ == "__main__":
    mock_event = {}
    mock_context = {}
    print(lambda_handler(mock_event, mock_context))
