import os
import sys
import json
from datetime import datetime, timezone
import pytz

# Add the 'src' folder to sys.path so that Python can find modules inside it
sys.path.append(os.path.join(os.getcwd(), "src"))

from src.main import main as run_sync_notion_and_google  # noqa: E402

# API Key
EXPECTED_API_KEY = os.environ.get("API_KEY")


def lambda_handler(event, context):
    """
    AWS Lambda Handler to always run the CLI without any parameters and include Perth timezone information.
    """
    try:
        # API Key check
        headers = event.get("headers", {})
        received_api_key = headers.get("x-api-key")

        if received_api_key != EXPECTED_API_KEY:
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: Invalid API Key"})}
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

        # Run the sync function without any parameters as default
        sync_result = run_sync_notion_and_google()

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "status": sync_result.get("status", "unknown"),
                    "message": sync_result.get("message", ""),
                    "utc_date": utc_date,
                    "utc_time": utc_time,
                    "utc_time_zone": utc_zone,
                    "perth_date": perth_date,
                    "perth_time": perth_time,
                    "perth_time_zone": perth_zone,
                }
            ),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e), "status": "Sync failed"}),
        }


# Mock event and context for local testing
if __name__ == "__main__":
    mock_event = {"headers": {"x-api-key": EXPECTED_API_KEY}}
    mock_context = {}
    print(lambda_handler(mock_event, mock_context))
