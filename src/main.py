import sys
import argparse
import json
from pathlib import Path
from google.auth.exceptions import RefreshError

# Ensure this module can import sibling packages when run as a script
sys.path.append(str(Path(__file__).resolve().parent))

from user_setting import update_notion_setting  # noqa: E402
from config.config import generate_uuid_config  # noqa: E402
from notion.notion_service import NotionService  # noqa: E402
from notion.notion_config import NotionConfig  # noqa: E402
from gcal.gcal_token import GoogleToken  # noqa: E402
from gcal.gcal_service import GoogleService  # noqa: E402
from utils.logging_utils import get_logger  # noqa: E402


def _result(status_code: int, status: str, message: str, extra: dict | None = None) -> dict:
    body = {"status": status, "message": message}
    if extra:
        body.update(extra)
    return {"statusCode": status_code, "body": body}


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
    logger = get_logger(__name__)

    current_dir = Path(__file__).parent.resolve()
    logger.info(f"Current directory: {current_dir}")

    # Initialize services
    try:
        logger.info(f"Using UUID: {uuid} (likely remote tokens)")
        config = generate_uuid_config(uuid)
        notion_config = NotionConfig(config, logger)
        notion_token = notion_config.token
        notion_user_setting = notion_config.user_setting
        notion_service = NotionService(notion_token, notion_user_setting, logger)
        google_token = GoogleToken(config, logger)
        google_service = GoogleService(notion_user_setting, google_token, logger)
    except RefreshError as e:
        logger.error("Google RefreshError during initialization", exc_info=True)
        # Let upstream handler decide how to surface refresh errors explicitly
        return _result(
            500,
            "init error",
            f"Google token refresh failed: {e}",
            {"stage": "init", "uuid": uuid, "error_type": type(e).__name__},
        )
    except Exception as e:
        logger.error("Error initializing services", exc_info=True)
        return _result(
            500,
            "init error",
            str(e),
            {"stage": "init", "uuid": uuid, "error_type": type(e).__name__},
        )

    # Parse CLI args (safe for lambda - argv is just script name)
    try:
        args = _parse_args()
    except Exception as e:
        logger.error("Error parsing arguments", exc_info=True)
        return _result(400, "arg error", str(e), {"stage": "argparse", "uuid": uuid})

    # Execute requested operation(s)
    try:
        res: dict | None = None
        if not args.timestamp and not args.google and not args.notion:
            logger.info("▶ Running sync with no arguments (default range)...")
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
            logger.info(f"▶ Syncing with timestamp range: {args.timestamp}")
            update_notion_setting.update_date_range(args.timestamp[0], args.timestamp[1])
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
            logger.info(f"▶ Forcing update: Notion from Google for {args.google}")
            update_notion_setting.update_date_range(args.google[0], args.google[1])
            from sync import sync

            res = sync.force_update_notion_tasks_by_google_event_and_ignore_time(
                user_setting=notion_config.user_setting,
                notion_service=notion_service,
                google_service=google_service,
            )

        if args.notion:
            logger.info(f"▶ Forcing update: Google from Notion for {args.notion}")
            update_notion_setting.update_date_range(args.notion[0], args.notion[1])
            from sync import sync

            res = sync.force_update_google_event_by_notion_task_and_ignore_time(
                user_setting=notion_config.user_setting,
                notion_service=notion_service,
                google_service=google_service,
            )

        # Ensure a response is always returned
        if res is None:
            return _result(500, "sync error", "No result returned from sync operation", {"stage": "execute"})
        return res
    except Exception as e:
        logger.error("Error during synchronization", exc_info=True)
        return _result(
            500,
            "sync error",
            str(e),
            {"stage": "execute", "uuid": uuid, "error_type": type(e).__name__},
        )


if __name__ == "__main__":
    # python -m src.main
    UUID = ""  # Replace with your UUID or leave empty for local
    response = main(UUID)
    print(json.dumps(response, indent=2))
