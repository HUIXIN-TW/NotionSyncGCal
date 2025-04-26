import sys
import argparse
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))
from user_setting import update_notion_setting  # noqa: E402
from config.config import CONFIG  # noqa: E402
from notion.notion_service import NotionService  # noqa: E402
from notion.notion_config import NotionConfig  # noqa: E402
from gcal.gcal_token import GoogleToken  # noqa: E402
from gcal.gcal_service import GoogleService  # noqa: E402

# Provide a rich console for printing inside `main()` even when not run as __main__
from rich.console import Console

console = Console()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent.resolve()
logger.info(f"Current directory: {CURRENT_DIR}")


def main():
    try:
        notion_config = NotionConfig(CONFIG, logger)
        notion_token = notion_config.token
        notion_user_setting = notion_config.user_setting
        notion_service = NotionService(notion_token, notion_user_setting, logger)
        google_token = GoogleToken(CONFIG, logger)
        google_service = GoogleService(notion_user_setting, google_token, logger)
    except Exception as e:
        logger.error(f"Error initializing services: {e}")
        return {"status": "error", "message": str(e)}  # safely converts exception to string

    try:
        parser = argparse.ArgumentParser(description="Welcome to Notion-Google Calendar Sync CLI!")

        # Adding optional arguments
        parser.add_argument(
            "-t",
            "--timestamp",
            nargs=2,
            type=int,
            help="Update Notion Task and Google Calendar By timestamp",
        )
        parser.add_argument(
            "-g",
            "--google",
            nargs=2,
            type=int,
            help="Force: Update Notion Task From Google Calendar",
        )
        parser.add_argument(
            "-n",
            "--notion",
            nargs=2,
            type=int,
            help="Force: Update Google Calendar From Notion Task",
        )

        args = parser.parse_args()
    except Exception as e:
        logger.error(f"Error parsing arguments: {e}")
        return {"status": "error", "message": str(e)}  # safely converts exception to string

    # Handling no arguments case
    try:
        if not args.timestamp and not args.google and not args.notion:
            console.print("[blue]▶ Running sync with [bold]no arguments[/bold] (default range)...")
            from sync import sync

            res = sync.synchronize_notion_and_google_calendar(
                user_setting=notion_user_setting,
                notion_service=notion_service,
                google_service=google_service,
                compare_time=True,
                should_update_notion_tasks=True,
                should_update_google_events=True,
            )
            return res

        # Handling optional -t flag for syncing by timestamp
        if args.timestamp:
            console.print(f"[blue]▶ Syncing with timestamp range:[/] [bold]{args.timestamp}[/]")
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
            return res

        # Handling optional -g flag for syncing from Google Calendar to Notion
        if args.google:
            console.print(f"[green]▶ Forcing update:[/] Notion for [bold]{args.google}[/]")
            update_notion_setting.update_date_range(args.google[0], args.google[1])
            from sync import sync

            res = sync.force_update_notion_tasks_by_google_event_and_ignore_time(
                user_setting=notion_config.user_setting,
                notion_service=notion_service,
                google_service=google_service,
            )
            return res

        # Handling optional -n flag for syncing from Notion to Google Calendar
        if args.notion:
            console.print(f"[cyan]▶ Forcing update:[/] Google Calendar for [bold]{args.notion}[/]")
            update_notion_setting.update_date_range(args.notion[0], args.notion[1])
            from sync import sync

            res = sync.force_update_google_event_by_notion_task_and_ignore_time(
                user_setting=notion_config.user_setting,
                notion_service=notion_service,
                google_service=google_service,
            )
            return res
    except Exception as e:
        logger.error(f"Error during synchronization: {e}")
        return {"status": "error", "message": str(e)}  # safely converts exception to string


if __name__ == "__main__":
    # python -m src.main
    res = main()
    console.print(res)
