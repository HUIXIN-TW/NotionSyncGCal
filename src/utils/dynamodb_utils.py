import os
import json
import time
from datetime import datetime, timezone
import boto3

USERS_TABLE = os.getenv("DYNAMODB_USER_TABLE")
LOGS_TABLE = os.getenv("DYNAMODB_SYNC_LOGS_TABLE")
REGION = os.getenv("APP_REGION")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def _get_tables():
    if not USERS_TABLE:
        raise ValueError("DYNAMODB_USER_TABLE env var is not set")
    if not LOGS_TABLE:
        raise ValueError("DYNAMODB_SYNC_LOGS_TABLE env var is not set")
    users_tbl = dynamodb.Table(USERS_TABLE)
    logs_tbl = dynamodb.Table(LOGS_TABLE)
    return users_tbl, logs_tbl


def save_sync_logs(uuid: str, response: dict, ttl_days: int = 7):
    now_iso = datetime.now(timezone.utc).isoformat()
    trigger_by = response.get("trigger_by", "unknown")
    log_str = json.dumps(response, ensure_ascii=False, default=str)
    now = datetime.now(timezone.utc)
    epoch_ms = int(now.timestamp() * 1000)
    ttl_sec = int(time.time()) + ttl_days * 24 * 60 * 60

    # update lastSyncLog in Users table + add log entry in Logs table
    users, logs = _get_tables()

    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%d")  # e.g. '2025-11-06'
    now_ms = int(now.timestamp() * 1000)  # epoch milliseconds
    users.update_item(
        Key={"uuid": uuid},
        UpdateExpression="SET lastSyncLog = :ls, updatedAt = :ua, updatedAtMs = :uams",
        ExpressionAttributeValues={
            ":ls": log_str,
            ":ua": now_iso,
            ":uams": now_ms,
        },
    )

    logs.put_item(
        Item={
            "uuid": uuid,  # partition key
            "date": now_iso,
            "timestamp": epoch_ms,
            "trigger_by": trigger_by,
            "log": log_str,
            "ttl": ttl_sec,
        }
    )


__all__ = [
    "save_sync_logs",
]
