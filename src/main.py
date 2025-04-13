import os
import argparse
from user_setting import update_notion_setting


def log_config_source():
    """Prints whether Notion and Google credentials are loaded from S3 or locally."""
    notion_source = (
        "S3" if (os.environ.get("S3_BUCKET_NAME") and os.environ.get("S3_NOTION_SETTINGS_PATH")) else "LOCAL"
    )

    google_token_source = (
        "S3" if (os.environ.get("S3_BUCKET_NAME") and os.environ.get("S3_CREDENTIALS_PATH")) else "LOCAL"
    )

    client_secret_source = (
        "S3" if (os.environ.get("S3_BUCKET_NAME") and os.environ.get("S3_CLIENT_SECRET_PATH")) else "LOCAL"
    )

    console.rule("[bold green]🔧 Configuration Source")
    console.print(f"[cyan]📘 Notion settings:[/]     [bold]{notion_source}[/]")
    console.print(f"[green]📅 Google token:[/]       [bold]{google_token_source}[/]")
    console.print(f"[yellow]🔐 Client secret:[/]     [bold]{client_secret_source}[/]")
    console.rule()


def main():
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

    # Handling no arguments case
    if not args.timestamp and not args.google and not args.notion:
        console.print("[blue]▶ Running sync with [bold]no arguments[/bold] (default range)...")
        from sync import sync

        sync.synchronize_notion_and_google_calendar()

    # Handling optional -t flag for syncing by timestamp
    if args.timestamp:
        console.print(f"[blue]▶ Syncing with timestamp range:[/] [bold]{args.timestamp}[/]")
        update_notion_setting.update_date_range(args.timestamp[0], args.timestamp[1])
        from sync import sync

        sync.synchronize_notion_and_google_calendar()

    # Handling optional -g flag for syncing from Google Calendar to Notion
    if args.google:
        console.print(f"[green]▶ Forcing update:[/] Google Calendar → Notion for [bold]{args.google}[/]")
        update_notion_setting.update_date_range(args.google[0], args.google[1])
        from sync import sync

        sync.force_update_notion_tasks_by_google_event_and_ignore_time()

    # Handling optional -n flag for syncing from Notion to Google Calendar
    if args.notion:
        console.print(f"[cyan]▶ Forcing update:[/] Notion → Google Calendar for [bold]{args.notion}[/]")
        update_notion_setting.update_date_range(args.notion[0], args.notion[1])
        from sync import sync

        sync.force_update_google_event_by_notion_task_and_ignore_time()


if __name__ == "__main__":
    from rich.console import Console

    console = Console()
    log_config_source()
    main()
