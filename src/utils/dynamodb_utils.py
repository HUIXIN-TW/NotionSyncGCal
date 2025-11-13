import os
import json
import time
from datetime import datetime, timezone
import boto3

USERS_TABLE = os.getenv("DYNAMODB_USER_TABLE")
LOGS_TABLE = os.getenv("DYNAMODB_SYNC_LOGS_TABLE")
GOOGLE_OAUTH_TOKEN_TABLE = os.getenv("DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE")
NOTION_OAUTH_TOKEN_TABLE = os.getenv("DYNAMODB_NOTION_OAUTH_TOKEN_TABLE")
REGION = os.getenv("APP_REGION")

dynamodb = boto3.resource("dynamodb", region_name=REGION)


def _get_logs_tables():
    if not USERS_TABLE:
        raise ValueError("DYNAMODB_USER_TABLE env var is not set")
    if not LOGS_TABLE:
        raise ValueError("DYNAMODB_SYNC_LOGS_TABLE env var is not set")
    users_tbl = dynamodb.Table(USERS_TABLE)
    logs_tbl = dynamodb.Table(LOGS_TABLE)
    return users_tbl, logs_tbl


def _get_google_tables():
    if not GOOGLE_OAUTH_TOKEN_TABLE:
        raise ValueError("DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE env var is not set")
    google_oauth_token_tbl = dynamodb.Table(GOOGLE_OAUTH_TOKEN_TABLE)
    return google_oauth_token_tbl


def _get_notion_tables():
    if not NOTION_OAUTH_TOKEN_TABLE:
        raise ValueError("DYNAMODB_NOTION_OAUTH_TOKEN_TABLE env var is not set")
    notion_oauth_token_tbl = dynamodb.Table(NOTION_OAUTH_TOKEN_TABLE)
    return notion_oauth_token_tbl


def save_sync_logs(uuid: str, response: dict, ttl_days: int = 7):
    now_iso = datetime.now(timezone.utc).isoformat()
    trigger_by = response.get("trigger_by", "unknown")
    log_str = json.dumps(response, ensure_ascii=False, default=str)
    now = datetime.now(timezone.utc)
    epoch_ms = int(now.timestamp() * 1000)
    ttl_sec = int(time.time()) + ttl_days * 24 * 60 * 60

    # update lastSyncLog in Users table + add log entry in Logs table
    users, logs = _get_logs_tables()

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


# get data from notion oauth token tables by uuid
def get_notion_token_by_uuid(uuid: str) -> str:
    notion_tbl = _get_notion_tables()
    response = notion_tbl.get_item(Key={"uuid": uuid})
    item = response.get("Item")
    if not item:
        raise ValueError(f"No Notion token found for uuid: {uuid}")
    return item


# get data from google oauth token tables by uuid
def get_google_token_by_uuid(uuid: str) -> str:
    google_tbl = _get_google_tables()
    response = google_tbl.get_item(Key={"uuid": uuid})
    item = response.get("Item")
    if not item:
        raise ValueError(f"No Google token found for uuid: {uuid}")
    return item


# update item in google oauth token tables by uuid
def update_google_token_by_uuid(uuid: str, access_token: str, refresh_token: str, expiry_date: str, updated_at: str):
    google_tbl = _get_google_tables()
    google_tbl.update_item(
        Key={"uuid": uuid},
        UpdateExpression="""
            SET accessToken = :at,
                refreshToken = :rt,
                expiryDate = :expiry,
                updatedAt = :updated
        """,
        ExpressionAttributeValues={
            ":at": access_token,
            ":rt": refresh_token,
            ":expiry": expiry_date,
            ":updated": updated_at,
        },
    )


__all__ = [
    "save_sync_logs",
    "get_notion_token_by_uuid",
    "get_google_token_by_uuid",
    "update_google_token_by_uuid",
]
