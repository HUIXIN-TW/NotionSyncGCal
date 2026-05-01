import os
import time
from datetime import datetime, timezone
import boto3
from utils.token_crypto import decrypt_token, encrypt_token


def _get_dynamodb():
    return boto3.resource("dynamodb", region_name=os.getenv("APP_REGION"))


def _get_users_table():
    users_table = os.getenv("DYNAMODB_USER_TABLE")
    if not users_table:
        raise ValueError("DYNAMODB_USER_TABLE env var is not set")
    users_tbl = _get_dynamodb().Table(users_table)
    return users_tbl


def _get_logs_tables():
    users_table = os.getenv("DYNAMODB_USER_TABLE")
    logs_table = os.getenv("DYNAMODB_SYNC_LOGS_TABLE")
    if not users_table:
        raise ValueError("DYNAMODB_USER_TABLE env var is not set")
    if not logs_table:
        raise ValueError("DYNAMODB_SYNC_LOGS_TABLE env var is not set")
    dynamodb = _get_dynamodb()
    users_tbl = dynamodb.Table(users_table)
    logs_tbl = dynamodb.Table(logs_table)
    return users_tbl, logs_tbl


def _get_google_tables():
    google_oauth_token_table = os.getenv("DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE")
    if not google_oauth_token_table:
        raise ValueError("DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE env var is not set")
    google_oauth_token_tbl = _get_dynamodb().Table(google_oauth_token_table)
    return google_oauth_token_tbl


def _get_notion_tables():
    notion_oauth_token_table = os.getenv("DYNAMODB_NOTION_OAUTH_TOKEN_TABLE")
    if not notion_oauth_token_table:
        raise ValueError("DYNAMODB_NOTION_OAUTH_TOKEN_TABLE env var is not set")
    notion_oauth_token_tbl = _get_dynamodb().Table(notion_oauth_token_table)
    return notion_oauth_token_tbl


def save_sync_logs(uuid: str, response: dict, ttl_days: int = 7):
    now_iso = datetime.now(timezone.utc).isoformat()
    trigger_by = response.get("trigger_by", "unknown")
    log_map = response  # use dict to store map data
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
            ":ls": log_map,
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
            "log": log_map,
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
    if "accessToken" in item:
        item["accessToken"] = decrypt_token(item.get("accessToken"))
    return item


# get data from google oauth token tables by uuid
def get_google_token_by_uuid(uuid: str) -> str:
    google_tbl = _get_google_tables()
    response = google_tbl.get_item(Key={"uuid": uuid})
    item = response.get("Item")
    if not item:
        raise ValueError(f"No Google token found for uuid: {uuid}")
    if "accessToken" in item:
        item["accessToken"] = decrypt_token(item.get("accessToken"))
    if "refreshToken" in item:
        item["refreshToken"] = decrypt_token(item.get("refreshToken"))
    return item


# update item in google oauth token tables by uuid
def update_google_token_by_uuid(uuid: str, access_token: str, refresh_token: str, expiry_date: str, updated_at: str):
    google_tbl = _get_google_tables()
    encrypted_access_token = encrypt_token(access_token)
    encrypted_refresh_token = encrypt_token(refresh_token)
    google_tbl.update_item(
        Key={"uuid": uuid},
        UpdateExpression="""
            SET accessToken = :at,
                refreshToken = :rt,
                expiryDate = :expiry,
                updatedAt = :updated
        """,
        ExpressionAttributeValues={
            ":at": encrypted_access_token,
            ":rt": encrypted_refresh_token,
            ":expiry": expiry_date,
            ":updated": updated_at,
        },
    )


# get notion config in user table by uuid
def get_notion_config_by_uuid(uuid: str) -> dict:
    users_tbl = _get_users_table()
    response = users_tbl.get_item(Key={"uuid": uuid})
    item = response.get("Item")
    if not item or "notionConfig" not in item:
        raise ValueError(f"No Notion config found for uuid: {uuid}")
    return item["notionConfig"]


# update notion config in user table by uuid
def update_notion_config_by_uuid(uuid: str, notion_config: dict):
    users_tbl = _get_users_table()
    users_tbl.update_item(
        Key={"uuid": uuid},
        UpdateExpression="SET notionConfig = :nc",
        ExpressionAttributeValues={
            ":nc": notion_config,
        },
    )


__all__ = [
    "save_sync_logs",
    "get_notion_token_by_uuid",
    "get_google_token_by_uuid",
    "update_google_token_by_uuid",
    "get_notion_config_by_uuid",
    "update_notion_config_by_uuid",
]
