import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TypedDict

MAX_SYNC_LOG_ERRORS = 3
SYNC_LOG_CONTRACT_VERSION = "2026-05-31.sync-log.v2"
SAFE_SYNC_FAILURE_MESSAGE = "Sync failed. See Lambda logs with aws_request_id for details."

# Sentinel used as the uuid field on SQS batch-aggregate summaries.
# It is never a real user UUID and must never be written to DynamoDB.
_BATCH_SUMMARY_UUID = "batch"


class SyncErrorPayload(TypedDict):
    action: str | None
    error_code: str
    error_message: str | None
    error: str | None
    gcal_event_start: str | None
    gcal_event_id: str | None
    notion_task_id: str | None
    retriable: bool | None


class RetryableSyncFailure(RuntimeError):
    """Raised when a trigger should fail for upstream retry or DLQ handling."""


def sanitize_sync_error(error: Any) -> SyncErrorPayload:
    if not isinstance(error, dict):
        return {
            "action": None,
            "error_code": "unstructured_sync_error",
            "error_message": str(error),
            "error": str(error),
            "gcal_event_start": None,
            "gcal_event_id": None,
            "notion_task_id": None,
            "retriable": None,
        }

    retriable = error.get("retriable")
    raw_error = error.get("error")
    error_message = error.get("error_message") or raw_error
    if retriable is True:
        # For provider/runtime failures we only expose machine-readable code + safe message.
        raw_error = None
        error_message = SAFE_SYNC_FAILURE_MESSAGE

    return {
        "action": error.get("action"),
        "error_code": error.get("error_code") or "unknown_sync_error",
        "error_message": error_message,
        "error": raw_error,
        "gcal_event_start": error.get("gcal_event_start"),
        "gcal_event_id": error.get("gcal_event_id"),
        "notion_task_id": error.get("notion_task_id"),
        "retriable": retriable,
    }


def sanitize_sync_log_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sanitized_payload = dict(payload)
    message = payload.get("message")
    status = payload.get("status")
    status_code = payload.get("statusCode")
    if isinstance(message, str):
        # Keep user-facing sync failures generic when upstream returned plaintext.
        if status == "sync_error" and isinstance(status_code, int) and status_code >= 500:
            sanitized_payload["message"] = {
                "error_code": "sync_runtime_error",
                "error_message": SAFE_SYNC_FAILURE_MESSAGE,
            }
        return sanitized_payload

    if not isinstance(message, dict):
        return sanitized_payload

    errors = message.get("errors")
    if not isinstance(errors, list):
        return sanitized_payload

    original_error_count = len(errors)
    sanitized_message = dict(message)
    sanitized_message["errors"] = [sanitize_sync_error(err) for err in errors[:MAX_SYNC_LOG_ERRORS]]
    sanitized_message["error_count"] = original_error_count
    sanitized_message["errors_truncated"] = original_error_count > MAX_SYNC_LOG_ERRORS
    sanitized_message["omitted_error_count"] = max(original_error_count - MAX_SYNC_LOG_ERRORS, 0)
    sanitized_payload["message"] = sanitized_message
    return sanitized_payload


def _iter_sync_errors(payload: Dict[str, Any]) -> list[Dict[str, Any]]:
    message = payload.get("message")
    if not isinstance(message, dict):
        return []

    errors = message.get("errors")
    if not isinstance(errors, list):
        return []

    return [error for error in errors if isinstance(error, dict)]


def sync_result_requires_retry(payload: Dict[str, Any]) -> bool:
    status_code = payload.get("statusCode")
    if isinstance(status_code, int) and status_code >= 500:
        return True

    return any(error.get("retriable") is True for error in _iter_sync_errors(payload))


def _save_sync_logs(uuid: str, payload: Dict[str, Any]) -> None:
    from .dynamodb_utils import save_sync_logs

    save_sync_logs(uuid, payload)


def process_and_log_sync_result(
    logger_obj,
    sync_result: Dict[str, Any],
    context: Any,
    uuid: str,
    lambda_start_time: datetime,
    trigger_name: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        status_code = int((sync_result or {}).get("statusCode", 500))
        body_obj = (sync_result or {}).get("body") or {}
        payload: Dict[str, Any] = {
            "contract_version": SYNC_LOG_CONTRACT_VERSION,
            "trigger_by": trigger_name,
            "uuid": uuid,
            "statusCode": status_code,
            "status": body_obj.get("status", "lambda_unknown_error"),
            "message": body_obj.get("message", "unknown"),
            "lambda_name": getattr(context, "function_name", "unknown"),
            "aws_request_id": getattr(context, "aws_request_id", "unknown"),
            "log_level": logger_obj.level,
            "duration_ms": int((datetime.now(timezone.utc) - lambda_start_time).total_seconds() * 1000),
        }
        if extra:
            payload.update(extra)
    except Exception:
        logger_obj.exception("Error processing sync result")
        payload = {
            "contract_version": SYNC_LOG_CONTRACT_VERSION,
            "trigger_by": trigger_name,
            "uuid": uuid,
            "statusCode": 500,
            "status": "lambda_processing_error",
            "message": "Error processing sync result",
            "lambda_name": getattr(context, "function_name", "unknown"),
            "aws_request_id": getattr(context, "aws_request_id", "unknown"),
            "log_level": logger_obj.level,
            "duration_ms": int((datetime.now(timezone.utc) - lambda_start_time).total_seconds() * 1000),
        }
    # Persist summary to DynamoDB; don't fail the handler on logging errors
    try:
        # _BATCH_SUMMARY_UUID is a sentinel for SQS aggregate results — never a real user UUID.
        # Batch summaries must never be written to DynamoDB as user sync logs.
        if uuid and uuid != _BATCH_SUMMARY_UUID:
            _save_sync_logs(uuid, sanitize_sync_log_payload(payload))
    except Exception:
        logger_obj.exception("Failed to persist sync summary to DynamoDB")
    return payload


def process_sqs_records(
    logger_obj,
    event: Dict[str, Any],
    context: Any,
    run_sync,
    lambda_start_time: datetime,
) -> Dict[str, Any]:
    """
    SQS batch processing: handle each record, summarize, and log
    """
    sqs_batch_results = []
    batch_item_failures = []
    logger_obj.debug(f"Processing SQS event with {len(event.get('Records', []))} records")

    # Process each SQS record
    for record in event["Records"]:
        logger_obj.debug(f"Processing SQS record: {record}")
        job_id = record.get("messageId", "unknown")
        provided_uuid = None
        try:
            body = json.loads(record.get("body", "{}"))
            provided_uuid = body.get("uuid")
            sync_result = run_sync(provided_uuid)
            processed_result = process_and_log_sync_result(
                logger_obj=logger_obj,
                sync_result=sync_result,
                context=context,
                uuid=provided_uuid,
                lambda_start_time=lambda_start_time,
                trigger_name="sqs",
                extra={"job_id": job_id},
            )
            sqs_batch_results.append(processed_result)
            if sync_result_requires_retry(processed_result):
                batch_item_failures.append({"itemIdentifier": job_id})
        except Exception:
            logger_obj.exception("Error processing SQS record")
            sqs_batch_results.append(
                {
                    "uuid": provided_uuid,
                    "job_id": job_id,
                    "statusCode": 500,
                    "error": "record processing failed",
                }
            )
            batch_item_failures.append({"itemIdentifier": job_id})

    # Summarize results for batch logging
    success_count = sum(1 for s in sqs_batch_results if not sync_result_requires_retry(s))
    failure_count = len(sqs_batch_results) - success_count

    # Emit a final batch summary log
    # Build enhanced batch summary avoiding duplicate 'results' key collisions
    success_uuids = [
        s.get("uuid")
        for s in sqs_batch_results
        if not sync_result_requires_retry(s)
    ]
    failure_uuids = [s.get("uuid") for s in sqs_batch_results if s.get("uuid") not in success_uuids]
    batch_sync_result = {
        # Provide an explicit statusCode for downstream handler uniformity
        "statusCode": 200,
        "body": {
            "status": "batch_processed",
            "message": (
                f"Processed {len(sqs_batch_results)} records: " f"{success_count} succeeded, {failure_count} failed."
            ),
        },
    }
    batch_summary = process_and_log_sync_result(
        logger_obj=logger_obj,
        sync_result=batch_sync_result,
        context=context,
        uuid=_BATCH_SUMMARY_UUID,
        lambda_start_time=lambda_start_time,
        trigger_name="sqs_batch",
        extra={
            "record_count": len(sqs_batch_results),
            "success_count": success_count,
            "failure_count": failure_count,
            "record_summaries": sqs_batch_results,  # concise per-record summary list
            "success_uuids": success_uuids,
            "failure_uuids": failure_uuids,
            "record_uuids": [u for u in success_uuids + failure_uuids if u],  # all uuids in order
        },
    )
    batch_summary["batchItemFailures"] = batch_item_failures
    return batch_summary


def process_eventbridge_event(
    logger_obj,
    event: Dict[str, Any],
    context: Any,
    run_sync,
    lambda_start_time: datetime,
) -> Dict[str, Any]:
    """
    Process EventBridge event.
    Returns a string summary of the event.
    """
    event_id = event.get("id", "unknown")
    detail_type = event.get("detail-type", "unknown")
    event_source = event.get("source", "unknown")
    event_time = event.get("time", "unknown")
    detail = event.get("detail", {})
    try:
        provided_uuid = detail.get("uuid")
        sync_result = run_sync(provided_uuid)
        result = process_and_log_sync_result(
            logger_obj=logger_obj,
            sync_result=sync_result,
            context=context,
            uuid=provided_uuid,
            lambda_start_time=lambda_start_time,
            trigger_name="eventbridge",
            extra={
                "event_id": event_id,
                "detail_type": detail_type,
                "source": event_source,
                "event_time": event_time,
            },
        )
        if sync_result_requires_retry(result):
            raise RetryableSyncFailure(
                "EventBridge sync produced retriable failure(s)."
            )
        return result
    except Exception:
        logger_obj.exception("Error processing EventBridge event")
        raise


def detect_event_source(logger_obj, event: dict) -> str:
    """
    Detect Lambda event source.
    Returns one of: 'sqs', 'api', 'eventbridge', or 'unknown'.
    """
    if not isinstance(event, dict):
        logger_obj.warning(f"Event is not a dict: {event}")
        return "unknown"

    # SQS: has 'Records' with eventSource = 'aws:sqs'
    if "Records" in event:
        record = event["Records"][0]
        logger_obj.debug(f"Detected SQS event: {event}")
        if record.get("eventSource") == "aws:sqs":
            return "sqs"

    # API Gateway v1/v2 or Lambda URL: presence of 'requestContext' and HTTP-like keys
    if "requestContext" in event:
        logger_obj.debug(f"Detected API Gateway or Lambda URL event: {event}")
        rc = event["requestContext"]
        if "httpMethod" in event or "http" in rc:
            return "api"

    # EventBridge (CloudWatch Events): has 'source' and 'detail-type'
    if "source" in event and "detail-type" in event:
        logger_obj.debug(f"Detected EventBridge event: {event}")
        return "eventbridge"

    logger_obj.warning(f"Could not detect event source from event: {event}")
    return "unknown"


__all__ = [
    "process_and_log_sync_result",
    "process_sqs_records",
    "process_eventbridge_event",
    "detect_event_source",
    "sync_result_requires_retry",
    "RetryableSyncFailure",
]
