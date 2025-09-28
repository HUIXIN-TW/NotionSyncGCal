import os
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict

from google.auth.exceptions import RefreshError

# Ensure the 'src' folder is importable when executed in different CWDs/environments
_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.append(_SRC)

# Import utility functions and helpers
from src.utils import get_logger  # noqa: E402
from src.utils.lambda_utils import (  # noqa: E402
    process_sqs_records,
    process_api_event,
)

# API key from environment variables
EXPECTED_API_KEY = os.environ.get("API_KEY", "")

# Set up logger to write to file
logger_obj = get_logger(__name__, log_file="tmp/sync_activity.log")


# Main Lambda handler: dispatch to SQS or API event processing
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler: dispatches to SQS or API helpers and centralises error handling."""
    lambda_start_time = datetime.now(timezone.utc)

    # Import here to preserve original lazy import behaviour used in the project
    from src.main import main as run_sync_notion_and_google  # noqa: E402

    try:
        if "Records" in event:
            message = process_sqs_records(logger_obj, event, context, run_sync_notion_and_google, lambda_start_time)
        else:
            message = process_api_event(
                logger_obj, event, context, run_sync_notion_and_google, lambda_start_time, EXPECTED_API_KEY
            )
        import rich

        rich.print(message)
        return message

    except RefreshError as e:
        logger_obj.exception(f"Google token refresh failed {e}")
    except Exception as e:
        logger_obj.exception(f"Unhandled lambda error {e}")


# --- Local test entrypoint ---
if __name__ == "__main__":
    # import pprint
    from dotenv import load_dotenv

    load_dotenv()
    EXPECTED_API_KEY = os.environ.get("API_KEY", "test-api-key")
    UUID = os.environ.get("UUID", "test-uuid")
    use_sqs_mock = False

    if use_sqs_mock:
        mock_event = {"Records": [{"body": json.dumps({"uuid": UUID})}]}
    else:
        mock_event = {"headers": {"x-api-key": EXPECTED_API_KEY}, "body": json.dumps({"uuid": UUID})}

    fake_ctx = type("FakeContext", (), {"function_name": "test-lambda", "aws_request_id": "abc-123"})()
    response = lambda_handler(mock_event, fake_ctx)
    # print(response) # return to sync table
