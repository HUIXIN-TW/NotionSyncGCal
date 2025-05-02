import os
import sys
import json
from datetime import datetime, timezone
from google.auth.exceptions import RefreshError
import pytz

# Add the 'src' folder to sys.path so that Python can find modules inside it
sys.path.append(os.path.join(os.getcwd(), "src"))

from src.main import main as run_sync_notion_and_google  # noqa: E402

# API Key
EXPECTED_API_KEY = os.environ.get("API_KEY")
ALLOWED_USERLIST = json.loads(os.environ.get("USERLIST", "[]"))


def lambda_handler(event, context):
    """
    AWS Lambda Handler to always run the CLI without any parameters and include Perth timezone information.
    """
    try:
        # API Key check: dynamic load from environment
        headers = event.get("headers", {})
        received_api_key = headers.get("x-api-key")
        if received_api_key != EXPECTED_API_KEY:
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: Invalid API Key"})}

        # User Check: parse body whether dict or JSON string
        raw_body = event.get("body", {})
        if isinstance(raw_body, str):
            body = json.loads(raw_body)
        else:
            body = raw_body
        provided_uuid = body.get("uuid", "")
        if provided_uuid and provided_uuid not in ALLOWED_USERLIST:
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: Invalid user UUID"})}

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
        sync_result = run_sync_notion_and_google(provided_uuid)
        if not sync_result:
            return {
                "statusCode": 500,
                "body": {"status": "lambda error", "message": "Sync function returned no result."},
            }
        sync_result_code = (sync_result.get("statusCode", 500),)
        sync_result_body = sync_result.get("body", {})
        return {
            "statusCode": sync_result_code,
            "body": json.dumps(
                {
                    "status": sync_result_body.get("status", "lambda unknown error"),
                    "message": sync_result_body.get("message", "unknown"),
                    "utc_date": utc_date,
                    "utc_time": utc_time,
                    "utc_time_zone": utc_zone,
                    "perth_date": perth_date,
                    "perth_time": perth_time,
                    "perth_time_zone": perth_zone,
                }
            ),
        }
    except RefreshError as e:
        return {"statusCode": 500, "body": {"status": f"Google token refresh failed: {str(e)}"}}
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "lambda error", "message": str(e)}),
        }


# Mock event and context for local testing
if __name__ == "__main__":
    expected_key = os.environ.get("API_KEY", "test-api-key")
    allowed_userlist = json.loads(os.environ.get("USERLIST", "[]"))[0]
    # Mock event with body as dict (no JSON string)
    mock_event = {
        "headers": {"x-api-key": expected_key},
        "body": {"uuid": allowed_userlist},
    }
    mock_context = {}
    print(lambda_handler(mock_event, mock_context))
