import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sync.contracts import (
    SyncErrorPayload,
    SyncExecutionResult,
    SyncOutcome,
    build_sync_result,
    classify_sync_result,
    get_result_message,
)

MAX_SYNC_LOG_ERRORS = 3
SYNC_LOG_CONTRACT_VERSION = "2026-05-31.sync-log.v2"
SAFE_SYNC_FAILURE_MESSAGE = "Sync failed. See Lambda logs with aws_request_id for details."

# Sentinel used as the uuid field on SQS batch-aggregate summaries.
# It is never a real user UUID and must never be written to DynamoDB.
_BATCH_SUMMARY_UUID = "batch"


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
        "source_id": error.get("source_id"),
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


def _save_sync_logs(uuid: str, payload: Dict[str, Any]) -> None:
    from .dynamodb_utils import save_sync_logs

    save_sync_logs(uuid, payload)


def process_and_log_sync_result(
    logger_obj,
    execution: SyncExecutionResult,
    context: Any,
    uuid: str,
    lambda_start_time: datetime,
    trigger_name: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        payload: Dict[str, Any] = {
            "contract_version": SYNC_LOG_CONTRACT_VERSION,
            "trigger_by": trigger_name,
            "uuid": uuid,
            "statusCode": execution.outcome.status_code,
            "status": execution.outcome.status,
            "message": get_result_message(execution.result) or "unknown",
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
    """Process an SQS batch using one typed outcome per record."""
    record_results: list[tuple[Dict[str, Any], SyncOutcome]] = []
    batch_item_failures = []
    logger_obj.debug(f"Processing SQS event with {len(event.get('Records', []))} records")

    for record in event["Records"]:
        logger_obj.debug(f"Processing SQS record: {record}")
        job_id = record.get("messageId", "unknown")
        provided_uuid = None
        try:
            body = json.loads(record.get("body", "{}"))
            if not isinstance(body, dict):
                raise ValueError("SQS body must be a JSON object.")
            if "execution" in body:
                raise ValueError("Legacy execution payload is not supported.")
            provided_uuid = body.get("uuid")
            if not isinstance(provided_uuid, str) or not provided_uuid.strip():
                raise ValueError("SQS body must contain a non-empty uuid.")

            execution = classify_sync_result(run_sync(provided_uuid))
            processed_result = process_and_log_sync_result(
                logger_obj=logger_obj,
                execution=execution,
                context=context,
                uuid=provided_uuid,
                lambda_start_time=lambda_start_time,
                trigger_name="sqs",
                extra={"job_id": job_id},
            )
            record_results.append((processed_result, execution.outcome))
            if execution.outcome.requires_retry:
                batch_item_failures.append({"itemIdentifier": job_id})
        except Exception:
            logger_obj.exception("Error processing SQS record")
            failed_result = {
                "uuid": provided_uuid,
                "job_id": job_id,
                "statusCode": 500,
                "error": "record processing failed",
            }
            failed_execution = classify_sync_result(
                build_sync_result(
                    500,
                    "sync_error",
                    {"error_code": "record_processing_failed", "retriable": True},
                )
            )
            record_results.append((failed_result, failed_execution.outcome))
            batch_item_failures.append({"itemIdentifier": job_id})

    success_count = sum(1 for _, outcome in record_results if outcome.counts_as_batch_success)
    retryable_failure_count = sum(1 for _, outcome in record_results if outcome.requires_retry)
    non_retriable_failure_count = len(record_results) - success_count - retryable_failure_count
    failure_count = retryable_failure_count + non_retriable_failure_count

    success_uuids = [result.get("uuid") for result, outcome in record_results if outcome.counts_as_batch_success]
    failure_uuids = [
        result.get("uuid") for result, outcome in record_results if not outcome.counts_as_batch_success
    ]
    batch_execution = classify_sync_result(
        build_sync_result(
            200,
            "batch_processed",
            f"Processed {len(record_results)} records: {success_count} succeeded, {failure_count} failed.",
        )
    )
    batch_summary = process_and_log_sync_result(
        logger_obj=logger_obj,
        execution=batch_execution,
        context=context,
        uuid=_BATCH_SUMMARY_UUID,
        lambda_start_time=lambda_start_time,
        trigger_name="sqs_batch",
        extra={
            "record_count": len(record_results),
            "success_count": success_count,
            "failure_count": failure_count,
            "retryable_failure_count": retryable_failure_count,
            "non_retriable_failure_count": non_retriable_failure_count,
            "record_summaries": [result for result, _ in record_results],
            "success_uuids": success_uuids,
            "failure_uuids": failure_uuids,
            "record_uuids": [u for u in success_uuids + failure_uuids if u],
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
        if not isinstance(detail, dict):
            raise ValueError("EventBridge detail must be an object.")
        if "execution" in detail:
            raise ValueError("Legacy execution payload is not supported.")
        provided_uuid = detail.get("uuid")
        if not isinstance(provided_uuid, str) or not provided_uuid.strip():
            raise ValueError("EventBridge detail must contain a non-empty uuid.")
        execution = classify_sync_result(run_sync(provided_uuid))
        result = process_and_log_sync_result(
            logger_obj=logger_obj,
            execution=execution,
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
        if execution.outcome.requires_retry:
            raise RetryableSyncFailure("EventBridge sync produced retriable failure(s).")
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
    "RetryableSyncFailure",
]
