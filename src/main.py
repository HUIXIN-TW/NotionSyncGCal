import argparse
from datetime import datetime, timedelta
import pytz
from user_setting import update_notion_setting

def convert_date_to_back_day_and_forward_day(given_date_str):
    # Given date
    given_date = datetime.strptime(given_date_str, "%Y-%m-%d")

    # Current date (today) in a specific time zone
    time_zone = pytz.timezone("Australia/Perth")
    current_date = datetime.now(time_zone).strftime("%Y-%m-%d")
    current_date = datetime.strptime(current_date, "%Y-%m-%d")

    # Calculate the difference in days
    day_difference = (given_date - current_date).days

    # Determine the go back and go forward values
    go_back_day = -day_difference
    go_forward = abs(day_difference) + 1

    print(f"Given date: {given_date.strftime('%Y-%m-%d')}")
    print(f"Current date (today): {current_date.strftime('%Y-%m-%d')}")
    print(f"go back_day = {go_back_day}, go forward = {go_forward}")

    return go_back_day, go_forward


def main():
    parser = argparse.ArgumentParser(
        description="Welcome to Notion-Google Calendar Sync CLI!"
    )

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
    parser.add_argument(
        "-e",
        "--explicit",
        nargs=1,
        type=str,
        help="Update: Notion Task and Google Calendar By timestamp on explicit date",
    )

    args = parser.parse_args()

    # Handling no arguments case
    if not args.timestamp and not args.google and not args.notion and not args.explicit:
        print("Running sync with no arguments")
        from sync import sync

        sync.synchronize_notion_and_google_calendar()

    # Handling optional -t flag for syncing by timestamp
    if args.timestamp:
        print(f"Running sync with timestamp: {args.timestamp}")
        update_notion_setting.update_date_range(args.timestamp[0], args.timestamp[1])
        from sync import sync

        sync.synchronize_notion_and_google_calendar()

    # Handling optional -g flag for syncing from Google Calendar to Notion
    if args.google:
        print(f"Running sync with Google Calendar to Notion: {args.google}")
        update_notion_setting.update_date_range(args.google[0], args.google[1])
        from sync import sync

        sync.force_update_notion_tasks_by_google_event_and_ignore_time()

    # Handling optional -n flag for syncing from Notion to Google Calendar
    if args.notion:
        print(f"Running sync with Notion to Google Calendar: {args.notion}")
        update_notion_setting.update_date_range(args.notion[0], args.notion[1])
        from sync import sync

        sync.force_update_google_event_by_notion_task_and_ignore_time()

    if args.explicit:
        print(f"Running sync with timestamp on {args.explicit[0]}")
        go_back_day, go_forward = convert_date_to_back_day_and_forward_day(args.explicit[0])
        update_notion_setting.update_date_range(go_back_day, go_forward)
        from sync import sync

        sync.synchronize_notion_and_google_calendar()

    print("Sync executed successfully!")


if __name__ == "__main__":
    main()
