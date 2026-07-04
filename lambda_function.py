import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from google.auth.exceptions import RefreshError

# Ensure the 'src' folder is importable when executed in different
# CWDs/environments.
_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.append(_SRC)

from src.utils import get_logger  # noqa: E402
from src.utils.lambda_utils import (  # noqa: E402
    detect_event_source,
    process_eventbridge_event,
    process_sqs_records,
)

logger_obj = get_logger(__name__)

SAFE_SYNC_FAILURE_MESSAGE = "Sync failed. See Lambda logs with aws_request_id for details."


def _all_sqs_batch_failures(event: Dict[str, Any]) -> list[Dict[str, str]]:
    failures = []
    for record in event.get("Records", []):
        if record.get("eventSource") == "aws:sqs":
            failures.append({"itemIdentifier": record.get("messageId", "unknown")})
    return failures


def _safe_error_payload(
    context: Any,
    error_code: str,
    status_code: int = 500,
) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": {
            "status": "sync_error",
            "message": {
                "error_code": error_code,
                "error_message": SAFE_SYNC_FAILURE_MESSAGE,
                "aws_request_id": getattr(context, "aws_request_id", "unknown"),
            },
        },
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Dispatch Lambda events and preserve trigger-specific failure semantics."""
    lambda_start_time = datetime.now(timezone.utc)
    event_type = "unknown"

    try:
        event_type = detect_event_source(logger_obj, event)
        if event_type == "api":
            logger_obj.warning("API event processing is not implemented for this Lambda.")
            return _safe_error_payload(
                context,
                "unsupported_event_source",
                status_code=501,
            )
        elif event_type == "sqs":
            from src.main import main as run_sync_notion_and_google  # noqa: E402

            return process_sqs_records(
                logger_obj,
                event,
                context,
                run_sync_notion_and_google,
                lambda_start_time,
            )
        elif event_type == "eventbridge":
            from src.main import main as run_sync_notion_and_google  # noqa: E402

            return process_eventbridge_event(
                logger_obj,
                event,
                context,
                run_sync_notion_and_google,
                lambda_start_time,
            )

        logger_obj.warning(f"Unknown event source: {event_type}")
        return {"statusCode": 400, "body": {"message": "Unknown event source"}}

    except RefreshError as e:
        logger_obj.exception(f"Google token refresh failed {e}")
        sqs_failures = _all_sqs_batch_failures(event)
        if sqs_failures:
            return {
                "batchItemFailures": sqs_failures,
                **_safe_error_payload(context, "google_refresh_error"),
            }
        if event_type != "eventbridge":
            return _safe_error_payload(context, "google_refresh_error")
        raise
    except Exception as e:
        logger_obj.exception(f"Unhandled lambda error {e}")
        sqs_failures = _all_sqs_batch_failures(event)
        if sqs_failures:
            return {
                "batchItemFailures": sqs_failures,
                **_safe_error_payload(context, "lambda_unhandled_error"),
            }
        if event_type != "eventbridge":
            return _safe_error_payload(context, "lambda_unhandled_error")
        raise


if __name__ == "__main__":
    UUID = ""
    mock_event = {"Records": [{"body": json.dumps({"uuid": UUID}), "eventSource": "aws:sqs"}]}
    fake_ctx = type(
        "FakeContext",
        (),
        {"function_name": "test-lambda", "aws_request_id": "abc-123"},
    )()
    response = lambda_handler(mock_event, fake_ctx)

    from pprint import pprint

    pprint(response)
