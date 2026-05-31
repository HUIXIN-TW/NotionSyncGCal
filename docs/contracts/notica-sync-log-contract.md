# Notica Sync Log Contract (Lambda -> notica-app)

Version: `2026-05-31.sync-log.v2`

This document defines the payload persisted as `lastSyncLog` in the Users table and emitted by `process_and_log_sync_result`.

## Top-level payload

Required keys:

- `contract_version: string`
- `trigger_by: string`
- `uuid: string | null`
- `statusCode: number`
- `status: string`
- `message: object | string`
- `lambda_name: string`
- `aws_request_id: string`
- `log_level: number`
- `duration_ms: number`

Optional keys:

- event-source specific fields such as `job_id`, `record_count`, `success_count`, `failure_count`, `record_summaries`, `success_uuids`, `failure_uuids`, `record_uuids`, `event_id`, `detail_type`, `source`, `event_time`

## Success message shape (`status = "sync_success"`)

`message` should be an object with:

- `summary: object`
- `trigger_time: string` (ISO-like timestamp)
- `errors: SyncError[]`

## SyncError shape

Required keys for each error item:

- `action: string | null`
- `error_code: string`
- `error_message: string | null`
- `error: string | null`
- `gcal_event_start: string | null`
- `gcal_event_id: string | null`
- `notion_task_id: string | null`
- `retriable: boolean | null`

Notes:

- Sanitization is applied before persistence to DynamoDB via `sanitize_sync_log_payload`.
- Lambda may return richer in-memory error objects, but persisted `lastSyncLog.message.errors[]` must conform to the shape above.
- `retriable = true` errors must not expose raw provider/runtime exception details in client-visible fields.
  Use a machine-readable `error_code` plus a safe `error_message` (`"Sync failed. See Lambda logs with aws_request_id for details."`).
- For `status = "sync_error"` with `statusCode >= 500`, persisted plaintext message strings are normalized to a safe
  object message: `{"error_code": "sync_runtime_error", "error_message": "Sync failed. See Lambda logs with aws_request_id for details."}`.
- Optional runtime-only field `debug_detail` may appear in non-production API responses when
  `EXPOSE_DEBUG_SYNC_ERRORS=true`. It is intentionally excluded from persisted `lastSyncLog.message.errors[]`.
- Contract changes must update this file and tests in `test/test_sync_log_contract.py`.
