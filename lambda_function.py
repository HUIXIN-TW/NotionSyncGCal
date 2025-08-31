import os
import sys
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.auth.exceptions import RefreshError

# Ensure the 'src' folder is importable when executed in different CWDs/environments
_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.append(_SRC)

from src.utils import get_timestamp, get_header, format_json_response, get_logger, log_json  # noqa: E402

# API key from environment variables
EXPECTED_API_KEY = os.environ.get("API_KEY", "")

logger = get_logger(__name__)


def _format_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    # Keep a thin wrapper so existing local calls remain unchanged
    return format_json_response(status_code, body)


def _log_invocation_summary(
    trigger: str,
    context: Any,
    start_time: datetime,
    status: str,
    message: str,
    ts: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "event": "sync_summary",
        "trigger": trigger,
        "lambda_name": getattr(context, "function_name", "unknown"),
        "aws_request_id": getattr(context, "aws_request_id", "unknown"),
        "duration_ms": int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
        "status": status,
        "message": message,
        **ts,
    }
    if extra:
        payload.update(extra)
    log_json(logger, payload)


def _handle_sync_result(
    sync_result: Dict[str, Any], context: Any, uuid: str, start_time: datetime, ts: Dict[str, Any], trigger: str
) -> Dict[str, Any]:
    """Format a sync_result into a lambda response and emit a structured log."""
    status_code = int(sync_result.get("statusCode", 500))
    body_obj = sync_result.get("body") or {}

    log = {
        "event": "sync_done",
        "trigger": trigger,
        "uuid": uuid,
        "status_code": status_code,
        "status": body_obj.get("status", "lambda unknown error"),
        "message": body_obj.get("message", "unknown"),
        "lambda_name": getattr(context, "function_name", "unknown"),
        "aws_request_id": getattr(context, "aws_request_id", "unknown"),
        "log_level": "INFO",
        "duration_ms": int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
        **ts,
    }
    log_json(logger, log)

    body = {
        "status": body_obj.get("status", "lambda unknown error"),
        "message": body_obj.get("message", "unknown"),
        **ts,
    }
    return _format_response(status_code, body)


def _process_sqs_records(event: Dict[str, Any], context: Any, run_sync, start_time: datetime) -> Dict[str, Any]:
    """Process SQS Records and return standard lambda response."""
    results = []
    for record in event["Records"]:
        provided_uuid = ""
        try:
            ts = get_timestamp()
            body = json.loads(record.get("body", "{}"))
            logger.info(f"SQS record: {body}")
            provided_uuid = (body.get("uuid") or "").strip()
            sync_result = run_sync(provided_uuid)
            results.append(_handle_sync_result(sync_result, context, provided_uuid, start_time, ts, trigger="sqs"))
        except Exception:
            logger.exception("Error processing SQS record")
            results.append({"uuid": provided_uuid, "error": "record processing failed"})

    # Build a slim summary for each result
    def _summarize_result(r: Dict[str, Any]) -> Dict[str, Any]:
        try:
            sc = int(r.get("statusCode", 500))
            body = r.get("body") or {}
            status = body.get("status") if isinstance(body, dict) else json.loads(body).get("status")
            message = body.get("message") if isinstance(body, dict) else json.loads(body).get("message")
            uuid = body.get("uuid") if isinstance(body, dict) else json.loads(body).get("uuid")
            return {"uuid": uuid, "status_code": sc, "status": status, "message": message}
        except Exception:
            return {"raw": r}

    summarized = [_summarize_result(r) for r in results]
    success_count = sum(
        1 for s in summarized if isinstance(s.get("status_code"), int) and s.get("status_code", 500) < 400
    )
    failure_count = len(results) - success_count

    batch_ts = get_timestamp()
    _log_invocation_summary(
        trigger="sqs",
        context=context,
        start_time=start_time,
        status="batch processed",
        message=f"Processed {len(results)} records: {success_count} success, {failure_count} failure",
        ts=batch_ts,
        extra={
            "record_count": len(results),
            "success_count": success_count,
            "failure_count": failure_count,
            "results": summarized,
        },
    )

    return _format_response(200, {"status": "batch processed", "results": results})


def _process_api_event(event: Dict[str, Any], context: Any, run_sync, start_time: datetime) -> Dict[str, Any]:
    """Validate API key, run a single sync and return formatted response."""
    headers = event.get("headers") or {}
    received_api_key = get_header(headers, "x-api-key", "")
    if received_api_key != EXPECTED_API_KEY:
        return _format_response(403, {"error": "Forbidden: Invalid API Key"})

    raw_body = event.get("body", {})
    try:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    except json.JSONDecodeError:
        body = {}

    provided_uuid = (body.get("uuid") or "").strip()
    sync_result = run_sync(provided_uuid)

    if not sync_result:
        return _format_response(500, {"status": "lambda error", "message": "Sync function returned no result."})

    ts = get_timestamp()
    response = _handle_sync_result(sync_result, context, provided_uuid, start_time, ts, trigger="api")
    # Log a final summary for API invocation
    try:
        resp_body = response.get("body")
        resp_obj = json.loads(resp_body) if isinstance(resp_body, str) else (resp_body or {})
        _log_invocation_summary(
            trigger="api",
            context=context,
            start_time=start_time,
            status=resp_obj.get("status", "unknown"),
            message=resp_obj.get("message", "unknown"),
            ts=ts,
            extra={"uuid": provided_uuid, "status_code": int(response.get("statusCode", 0))},
        )
    except Exception:
        logger.exception("Failed to emit API summary log")
    return response


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler (thin): dispatches to SQS or API helpers and centralises error handling."""
    start_time = datetime.now(timezone.utc)

    # Import here to preserve original lazy import behaviour used in the project
    from src.main import main as run_sync_notion_and_google  # noqa: E402

    try:
        if "Records" in event:
            return _process_sqs_records(event, context, run_sync_notion_and_google, start_time)

        return _process_api_event(event, context, run_sync_notion_and_google, start_time)

    except RefreshError as e:
        logger.exception("Google token refresh failed")
        # Emit a final summary log on fatal init/refresh errors
        try:
            ts = get_timestamp()
            trigger = "sqs" if isinstance(event, dict) and "Records" in event else "api"
            extra = {"status_code": 500}
            if trigger == "sqs":
                extra.update({"record_count": len(event.get("Records", []))})
            else:
                # try to extract uuid from body
                try:
                    raw_body = event.get("body", {})
                    body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
                    extra.update({"uuid": (body.get("uuid") or "").strip()})
                except Exception:
                    pass
            _log_invocation_summary(trigger, context, start_time, "Google token refresh failed", str(e), ts, extra)
        except Exception:
            logger.exception("Failed to emit summary for RefreshError")
        return _format_response(500, {"status": "Google token refresh failed", "message": str(e)})
    except Exception as e:
        logger.exception("Unhandled lambda error")
        # Emit a final summary log on fatal errors
        try:
            ts = get_timestamp()
            trigger = "sqs" if isinstance(event, dict) and "Records" in event else "api"
            extra = {"status_code": 500}
            if trigger == "sqs":
                extra.update({"record_count": len(event.get("Records", []))})
            else:
                try:
                    raw_body = event.get("body", {})
                    body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
                    extra.update({"uuid": (body.get("uuid") or "").strip()})
                except Exception:
                    pass
            _log_invocation_summary(trigger, context, start_time, "lambda error", str(e), ts, extra)
        except Exception:
            logger.exception("Failed to emit summary for unhandled error")
        return _format_response(500, {"status": "lambda error", "message": str(e)})


# --- Local test entrypoint ---
if __name__ == "__main__":
    expected_key = os.environ.get("API_KEY", "test-api-key")
    use_sqs_mock = True

    if use_sqs_mock:
        mock_event = {
            "Records": [{"body": json.dumps({"uuid": "test-uuid-1"})}, {"body": json.dumps({"uuid": "test-uuid-2"})}]
        }
    else:
        mock_event = {"headers": {"x-api-key": expected_key}, "body": json.dumps({"uuid": "test-uuid"})}

    fake_ctx = type("FakeContext", (), {"function_name": "test-lambda", "aws_request_id": "abc-123"})()
    print(lambda_handler(mock_event, fake_ctx))
