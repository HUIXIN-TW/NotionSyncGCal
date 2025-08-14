import os
import sys
import json
from datetime import datetime, timezone
from google.auth.exceptions import RefreshError
import pytz

# Add the 'src' folder to sys.path so Python can import modules inside it
sys.path.append(os.path.join(os.getcwd(), "src"))

# API key from environment variables
EXPECTED_API_KEY = os.environ.get("API_KEY", "")


def get_timestamp():
    """
    Returns current time information in both UTC and Perth timezones.
    """
    # UTC time
    now_utc = datetime.now(timezone.utc)
    utc_date = now_utc.strftime("%Y-%m-%d")
    utc_time = now_utc.strftime("%H:%M:%S")
    utc_zone = now_utc.tzname()

    # Perth time
    perth_tz = pytz.timezone("Australia/Perth")
    now_perth = datetime.now(perth_tz)
    perth_date = now_perth.strftime("%Y-%m-%d")
    perth_time = now_perth.strftime("%H:%M:%S")
    perth_zone = now_perth.tzname()

    return {
        "utc_date": utc_date,
        "utc_time": utc_time,
        "utc_time_zone": utc_zone,
        "perth_date": perth_date,
        "perth_time": perth_time,
        "perth_time_zone": perth_zone,
        "epoch_ms": int(now_utc.timestamp() * 1000),
    }


def _get_header(headers: dict, key: str, default=None):
    """
    Retrieves a header value in a case-insensitive manner.
    """
    if not headers:
        return default
    lower = {k.lower(): v for k, v in headers.items()}
    return lower.get(key.lower(), default)


def lambda_handler(event, context):
    """
    AWS Lambda handler to run the sync process and return timestamped results.
    Supports:
    - SQS trigger: {"Records": [...]}
    - API Gateway trigger with x-api-key and JSON body
    """
    try:
        # Start Timestamp
        start_time = datetime.now(timezone.utc)

        from src.main import main as run_sync_notion_and_google  # noqa: E402

        # --- Handle SQS-triggered event ---
        if "Records" in event:
            results = []
            for record in event["Records"]:
                try:
                    ts = get_timestamp()
                    body = json.loads(record["body"])
                    print(f'SQS record:  {body}')
                    provided_uuid = (body.get("uuid") or "").strip()
                    sync_result = run_sync_notion_and_google(provided_uuid)

                    result = _handle_sync_result(sync_result, context, provided_uuid, start_time, ts)
                    results.append(result)
                except Exception as e:
                    results.append({"uuid": provided_uuid, "error": str(e)})

            return {
                "statusCode": 200,
                "body": json.dumps({"status": "batch processed", "results": results}),
            }

        # --- Handle API Gateway-style event ---
        headers = event.get("headers") or {}
        received_api_key = _get_header(headers, "x-api-key", "")
        if received_api_key != EXPECTED_API_KEY:
            return {"statusCode": 403, "body": json.dumps({"error": "Forbidden: Invalid API Key"})}

        raw_body = event.get("body", {})
        try:
            body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
        except json.JSONDecodeError:
            body = {}

        provided_uuid = (body.get("uuid") or "").strip()
        sync_result = run_sync_notion_and_google(provided_uuid)

        if not sync_result:
            return {
                "statusCode": 500,
                "body": json.dumps({"status": "lambda error", "message": "Sync function returned no result."}),
            }

        status_code = int(sync_result.get("statusCode", 500))
        body_obj = sync_result.get("body") or {}
        ts = get_timestamp()

        # Structured logging
        print(
            json.dumps(
                {
                    "event": "sync_done",
                    "uuid": provided_uuid,
                    "status_code": status_code,
                    "status": body_obj.get("status", "lambda unknown error"),
                    "message": body_obj.get("message", "unknown"),
                    "lambda_name": context.function_name,
                    "aws_request_id": context.aws_request_id,
                    "log_level": "INFO",
                    "duration_ms": int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
                    **ts,
                }
            )
        )

        return {
            "statusCode": status_code,
            "body": json.dumps(
                {
                    "status": body_obj.get("status", "lambda unknown error"),
                    "message": body_obj.get("message", "unknown"),
                    **ts,
                }
            ),
        }

    except RefreshError as e:
        # Specific Google refresh error
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "Google token refresh failed", "message": str(e)}),
        }
    except Exception as e:
        # Generic error
        print(json.dumps({"event": "unhandled_error", "error": str(e), **get_timestamp()}))
        return {
            "statusCode": 500,
            "body": json.dumps({"status": "lambda error", "message": str(e)}),
        }


def _handle_sync_result(sync_result, context, uuid, start_time, ts):
    """
    Shared logging and response formatting for sync results.
    """
    status_code = int(sync_result.get("statusCode", 500))
    body_obj = sync_result.get("body") or {}

    log = {
        "event": "sync_done",
        "uuid": uuid,
        "status_code": status_code,
        "status": body_obj.get("status", "lambda unknown error"),
        "message": body_obj.get("message", "unknown"),
        "lambda_name": context.function_name,
        "aws_request_id": context.aws_request_id,
        "log_level": "INFO",
        "duration_ms": int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
        **ts,
    }
    print(json.dumps(log))

    return {
        "statusCode": status_code,
        "body": json.dumps(
            {
                "status": body_obj.get("status", "lambda unknown error"),
                "message": body_obj.get("message", "unknown"),
                **ts,
            }
        ),
    }

# --- Local test entrypoint ---
if __name__ == "__main__":
    expected_key = os.environ.get("API_KEY", "test-api-key")

    use_sqs_mock = True

    if use_sqs_mock:
        mock_event = {
            "Records": [
                {"body": json.dumps({"uuid": "test-uuid-1"})},
                {"body": json.dumps({"uuid": "test-uuid-2"})},
            ]
        }
    else:
        mock_event = {
            "headers": {"x-api-key": expected_key},
            "body": json.dumps({"uuid": "test-uuid"}),
        }

    print(lambda_handler(mock_event, type("FakeContext", (), {"function_name": "test-lambda", "aws_request_id": "abc-123"})()))
