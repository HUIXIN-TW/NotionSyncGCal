import os
import sys
import argparse
import json
from pathlib import Path
import boto3
from google.auth.exceptions import RefreshError

# Ensure this module can import sibling packages when run as a script
sys.path.append(str(Path(__file__).resolve().parent))

from user_setting import update_local_notion_setting  # noqa: E402
from config.config import generate_config  # noqa: E402
from notion.notion_service import NotionService  # noqa: E402
from notion.notion_config import NotionConfig  # noqa: E402
from notion.notion_token import NotionToken  # noqa: E402
from gcal.gcal_token import GoogleToken  # noqa: E402
from gcal.gcal_service import GoogleService  # noqa: E402
from utils.logging_utils import get_logger  # noqa: E402


def _parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Welcome to Notion-Google Calendar Sync CLI!")
    parser.add_argument(
        "-t",
        "--timestamp",
        nargs=2,
        type=int,
        help="Update Notion Task and Google Calendar by timestamp [start end]",
    )
    parser.add_argument(
        "-g",
        "--google",
        nargs=2,
        type=int,
        help="Force: Update Notion Task from Google Calendar [start end]",
    )
    parser.add_argument(
        "-n",
        "--notion",
        nargs=2,
        type=int,
        help="Force: Update Google Calendar from Notion Task [start end]",
    )
    return parser.parse_args(argv)


def main(uuid: str | None = None) -> dict:
    logger = get_logger(__name__, log_file=os.getenv("LOG_FILE_PATH"))

    current_dir = Path(__file__).parent.resolve()
    logger.debug(f"Current directory: {current_dir}")

    # Initialize services
    try:
        logger.debug(f"Using UUID: {uuid}")

        # Configure paths based on UUID (local vs S3)
        config = generate_config(uuid)

        # Notion
        notion_config = NotionConfig(config, logger)
        notion_token = NotionToken(config, logger).get()
        notion_user_setting = notion_config.user_setting
        notion_service = NotionService(notion_token, notion_user_setting, logger)

        # Google
        google_token = GoogleToken(config, logger)
        google_service = GoogleService(notion_user_setting, google_token, logger)
    except RefreshError as e:
        logger.error(f"Google RefreshError during initialization: {e}")
    except Exception as e:
        logger.error(f"Error initializing services: {e}")

    # Parse CLI args (safe for lambda - argv is just script name)
    try:
        args = _parse_args()
        logger.debug(f"Parsed arguments: {args}")
    except Exception as e:
        logger.error(f"Error parsing arguments: {e}")

    # Execute requested operation(s)
    try:
        res: dict | None = None
        if not args.timestamp and not args.google and not args.notion:
            logger.debug("▶ Running sync with no arguments (default range)...")
            from sync import sync

            res = sync.synchronize_notion_and_google_calendar(
                user_setting=notion_user_setting,
                notion_service=notion_service,
                google_service=google_service,
                compare_time=True,
                should_update_notion_tasks=True,
                should_update_google_events=True,
            )

        if args.timestamp:
            logger.debug(f"▶ Syncing with timestamp range: {args.timestamp}")
            update_local_notion_setting.update_date_range(args.timestamp[0], args.timestamp[1])
            from sync import sync

            res = sync.synchronize_notion_and_google_calendar(
                user_setting=notion_user_setting,
                notion_service=notion_service,
                google_service=google_service,
                compare_time=True,
                should_update_notion_tasks=True,
                should_update_google_events=True,
            )

        if args.google:
            logger.debug(f"▶ Forcing update: Notion from Google for {args.google}")
            update_local_notion_setting.update_date_range(args.google[0], args.google[1])
            from sync import sync

            res = sync.force_update_notion_tasks_by_google_event_and_ignore_time(
                user_setting=notion_config.user_setting,
                notion_service=notion_service,
                google_service=google_service,
            )

        if args.notion:
            logger.debug(f"▶ Forcing update: Google from Notion for {args.notion}")
            update_local_notion_setting.update_date_range(args.notion[0], args.notion[1])
            from sync import sync

            res = sync.force_update_google_event_by_notion_task_and_ignore_time(
                user_setting=notion_config.user_setting,
                notion_service=notion_service,
                google_service=google_service,
            )
        return res
    except Exception as e:
        logger.error(f"Error during sync operation {e}")


if __name__ == "__main__":
    # python -m src.main
    UUID = "huixinyang"  # Replace with your UUID or leave empty for local
    response = main(UUID)
    # update response into dynamoDB "NotionSyncGCalUser" table with uuid
    if response:
        dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
        table_name = os.getenv("DYNAMODB_TABLE_NAME", "NotionSyncGCalUser")
        table = dynamodb.Table(table_name)
        table.put_item(Item={"uuid": UUID, "last_sync_response": response})
        logger = get_logger(__name__, log_file=os.getenv("LOG_FILE_PATH"))
        logger.info(f"Sync response stored in DynamoDB table {table_name} for UUID {UUID}")
    print(json.dumps(response, indent=2))