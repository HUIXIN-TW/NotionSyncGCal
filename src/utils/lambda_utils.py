import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .dynamodb_utils import save_sync_logs  # noqa: E402


def process_and_log_sync_result(
    logger_obj,
    sync_result: Dict[str, Any],
    context: Any,
    uuid: str,
    lambda_start_time: datetime,
    trigger_name: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    statusCode = int(sync_result.get("statusCode", 500))
    body_obj = sync_result.get("body") or {}
    payload: Dict[str, Any] = {
        "trigger_by": trigger_name,
        "uuid": uuid,
        "statusCode": statusCode,
        "status": body_obj.get("status", "lambda_unknown_error"),
        "message": body_obj.get("message", "unknown"),
        "lambda_name": getattr(context, "function_name", "unknown"),
        "aws_request_id": getattr(context, "aws_request_id", "unknown"),
        "log_level": logger_obj.level,
        "duration_ms": int((datetime.now(timezone.utc) - lambda_start_time).total_seconds() * 1000),
    }
    if extra:
        payload.update(extra)
    # Persist summary to DynamoDB; don't fail the handler on logging errors
    try:
        # Only log individual user syncs, not batch summaries
        if uuid and uuid != "batch":
            save_sync_logs(uuid, payload)  # ttl default 7 days
    except Exception:
        logger_obj.exception("Failed to persist sync summary to DynamoDB")
    return payload


def process_sqs_records(
    logger_obj, event: Dict[str, Any], context: Any, run_sync, lambda_start_time: datetime
) -> Dict[str, Any]:
    """
    SQS batch processing: handle each record, summarize, and log
    """
    sqs_batch_results = []
    logger_obj.debug(f"Processing SQS event with {len(event.get('Records', []))} records")

    # Process each SQS record
    for record in event["Records"]:
        logger_obj.debug(f"Processing SQS record: {record}")
        try:
            body = json.loads(record.get("body", "{}"))
            job_id = record.get("messageId", "unknown")
            provided_uuid = body.get("uuid")
            sync_result = run_sync(provided_uuid)
            sqs_batch_results.append(
                process_and_log_sync_result(
                    logger_obj=logger_obj,
                    sync_result=sync_result,
                    context=context,
                    uuid=provided_uuid,
                    lambda_start_time=lambda_start_time,
                    trigger_name="sqs",
                    extra={"job_id": job_id},
                )
            )
        except Exception:
            logger_obj.exception("Error processing SQS record")
            sqs_batch_results.append({"uuid": provided_uuid, "error": "record processing failed"})

    # Summarize results for batch logging
    success_count = sum(
        1 for s in sqs_batch_results if isinstance(s.get("statusCode"), int) and s.get("statusCode", 500) < 400
    )
    failure_count = len(sqs_batch_results) - success_count

    # Emit a final batch summary log
    # Build enhanced batch summary avoiding duplicate 'results' key collisions
    success_uuids = [
        s.get("uuid")
        for s in sqs_batch_results
        if isinstance(s.get("statusCode"), int) and s.get("statusCode", 500) < 400
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
    return process_and_log_sync_result(
        logger_obj=logger_obj,
        sync_result=batch_sync_result,
        context=context,
        uuid="batch",
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


def process_eventbridge_event(
    logger_obj, event: Dict[str, Any], context: Any, run_sync, lambda_start_time: datetime
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
            extra={"event_id": event_id, "detail_type": detail_type, "source": event_source, "event_time": event_time},
        )
        return result
    except Exception:
        logger_obj.exception("Error processing EventBridge event")
        return {"statusCode": 500, "body": {"error": "Event processing failed"}}


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


__all__ = ["process_and_log_sync_result", "process_sqs_records", "detect_event_source"]
