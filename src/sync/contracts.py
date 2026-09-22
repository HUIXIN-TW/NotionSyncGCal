from typing import Any, TypedDict


SYNC_CAPACITY_LIMIT_ERROR_CODE = "sync_capacity_limit_exceeded"


class SyncErrorPayload(TypedDict, total=False):
    source_id: str | None
    action: str | None
    error_code: str
    error_message: str | None
    error: str | None
    gcal_event_start: str | None
    gcal_event_id: str | None
    notion_task_id: str | None
    retriable: bool | None
    debug_detail: str


class SyncSuccessMessage(TypedDict, total=False):
    summary: dict[str, Any]
    trigger_time: str
    errors: list[SyncErrorPayload]
    error_code: str
    error_message: str
    limit: int
    google_event_count: int
    notion_task_count: int
    capacity_limited: bool
    retriable: bool


class SyncResultBody(TypedDict):
    status: str
    message: str | dict[str, Any]


class SyncResult(TypedDict):
    statusCode: int
    body: SyncResultBody


def build_sync_error(
    action: str | None,
    error_code: str,
    *,
    error_message: str | None = None,
    error: str | None = None,
    notion_task_id: str | None = None,
    gcal_event_id: str | None = None,
    gcal_event_start: str | None = None,
    retriable: bool | None = None,
    debug_detail: str | None = None,
) -> SyncErrorPayload:
    message = error_message if error_message is not None else error
    payload: SyncErrorPayload = {
        "action": action,
        "error_code": error_code,
        "error_message": message,
        "error": error,
        "notion_task_id": notion_task_id,
        "gcal_event_id": gcal_event_id,
        "gcal_event_start": gcal_event_start,
        "retriable": retriable,
    }
    if debug_detail is not None:
        payload["debug_detail"] = debug_detail
    return payload


def build_sync_result(status_code: int, status: str, message: str | dict[str, Any]) -> SyncResult:
    return {
        "statusCode": status_code,
        "body": {
            "status": status,
            "message": message,
        },
    }


def build_capacity_limited_result(
    *,
    sync_task_limit: int,
    trigger_sync_time: str,
    event_count: int,
    task_count: int,
) -> SyncResult:
    error_message = (
        f"Sync input volume exceeds the supported limit of {sync_task_limit} items. "
        "The sync was skipped intentionally to avoid an oversized run."
    )
    return build_sync_result(
        200,
        "sync_success",
        {
            "error_code": SYNC_CAPACITY_LIMIT_ERROR_CODE,
            "error_message": error_message,
            "limit": sync_task_limit,
            "google_event_count": event_count,
            "notion_task_count": task_count,
            "trigger_time": trigger_sync_time,
            "capacity_limited": True,
            "retriable": False,
            "errors": [
                build_sync_error(
                    "sync_capacity_guard",
                    SYNC_CAPACITY_LIMIT_ERROR_CODE,
                    error_message=error_message,
                    error=None,
                    gcal_event_start=None,
                    gcal_event_id=None,
                    notion_task_id=None,
                    retriable=False,
                )
            ],
        },
    )


def get_result_status(sync_result: dict[str, Any] | None) -> str:
    if "status" in (sync_result or {}):
        return sync_result.get("status", "lambda_unknown_error")
    body = (sync_result or {}).get("body") or {}
    return body.get("status", "lambda_unknown_error")


def get_result_message(sync_result: dict[str, Any] | None) -> Any:
    if "message" in (sync_result or {}):
        return sync_result.get("message")
    body = (sync_result or {}).get("body") or {}
    return body.get("message")


def is_retryable_result(sync_result: dict[str, Any] | None) -> bool:
    status_code = int((sync_result or {}).get("statusCode", 500))
    if status_code >= 500:
        return True

    message = get_result_message(sync_result)
    if isinstance(message, dict):
        if message.get("retriable") is True:
            return True

        errors = message.get("errors")
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, dict) and error.get("retriable") is True:
                    return True
    return False


def is_successful_result(sync_result: dict[str, Any] | None) -> bool:
    status_code = int((sync_result or {}).get("statusCode", 500))
    if status_code >= 400 or is_retryable_result(sync_result):
        return False
    return get_result_status(sync_result) in {"sync_success", "batch_processed"}


__all__ = [
    "SYNC_CAPACITY_LIMIT_ERROR_CODE",
    "SyncErrorPayload",
    "SyncResult",
    "SyncResultBody",
    "SyncSuccessMessage",
    "build_capacity_limited_result",
    "build_sync_error",
    "build_sync_result",
    "get_result_message",
    "get_result_status",
    "is_retryable_result",
    "is_successful_result",
]
