import os, json, time
from datetime import datetime, timezone
import boto3

USERS_TABLE = os.getenv("DYNAMODB_USER_TABLE")
LOGS_TABLE  = os.getenv("DYNAMODB_SYNC_LOGS_TABLE")
REGION = os.getenv("APP_REGION")

dynamodb = boto3.resource("dynamodb", region_name=REGION)

def _get_tables():
    if not USERS_TABLE:
        raise ValueError("DYNAMODB_USER_TABLE env var is not set")
    if not LOGS_TABLE:
        raise ValueError("DYNAMODB_SYNC_LOGS_TABLE env var is not set")
    users_tbl = dynamodb.Table(USERS_TABLE)
    logs_tbl  = dynamodb.Table(LOGS_TABLE)
    return users_tbl, logs_tbl

def save_sync_logs(uuid: str, response: dict, ttl_days: int = 7):
    now_iso = datetime.now(timezone.utc).isoformat()
    log_str = json.dumps(response, ensure_ascii=False, default=str)
    now = datetime.now(timezone.utc)
    epoch_ms = int(now.timestamp() * 1000)        # <-- Sort key: Number
    ttl_sec  = int(time.time()) + ttl_days * 24 * 60 * 60

    # update lastSyncLog in Users table + add log entry in Logs table
    users, logs = _get_tables()
    users.update_item(
        Key={"uuid": uuid},
        UpdateExpression="SET lastSyncLog = :ls, updatedAt = :ua",
        ExpressionAttributeValues={":ls": log_str, ":ua": now_iso},
    )

    logs.put_item(
        Item={
            "uuid": uuid, # partition key
            "timestamp": epoch_ms, # sort key
            "log":  log_str,
            "ttl":  ttl_sec,
        }
    )
__all__ = [
    "save_sync_logs",
]
