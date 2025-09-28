import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from src.utils.http_utils import get_header


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
        "status": body_obj.get("status", "lambda unknown error"),
        "message": body_obj.get("message", "unknown"),
        "lambda_name": getattr(context, "function_name", "unknown"),
        "aws_request_id": getattr(context, "aws_request_id", "unknown"),
        "log_level": logger_obj.level,
        "duration_ms": int((datetime.now(timezone.utc) - lambda_start_time).total_seconds() * 1000),
    }
    if extra:
        payload.update(extra)
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
            "status": "batch processed",
            "message": (
                f"Processed {len(sqs_batch_results)} records: "
                f"{success_count} succeeded, {failure_count} failed."
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


def process_api_event(
    logger_obj, event: Dict[str, Any], context: Any, run_sync, lambda_start_time: datetime, expected_api_key: str
) -> Dict[str, Any]:
    """
    API Gateway event processing: validate key, run sync, log summary
    """
    headers = event.get("headers") or {}
    received_api_key = get_header(headers, "x-api-key", "")
    if received_api_key != expected_api_key:
        return {"statusCode": 403, "body": {"error": "Forbidden: Invalid API Key"}}

    raw_body = event.get("body", {})
    try:
        body = json.loads(raw_body) if isinstance(raw_body, str) else (raw_body or {})
    except json.JSONDecodeError:
        body = {}

    provided_uuid = (body.get("uuid") or "").strip()
    sync_result = run_sync(provided_uuid)

    if not sync_result:
        return {"statusCode": 500, body: {"status": "lambda error", "message": "Sync function returned no result."}}

    response = process_and_log_sync_result(
        logger_obj=logger_obj,
        sync_result=sync_result,
        context=context,
        uuid=provided_uuid,
        lambda_start_time=lambda_start_time,
        trigger_name="api",
    )
    return response


__all__ = [
    "process_and_log_sync_result",
    "process_sqs_records",
    "process_api_event",
]
