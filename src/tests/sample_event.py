import notion_token
import notion_services
import gcal_token
import json
from datetime import datetime, timedelta
import pytz

# Initialize the Notion token
nt = notion_token.Notion()
gt = gcal_token.Google()


def notion_event_sample(num=1):
    count = 0
    resultList = notion_services.queryNotionEvent_all()
    if len(resultList) > 1:
        for i, el in enumerate(resultList):
            if count < num:
                count = count + 1
                print(f"{i}th Query Notion Event")
                print(json.dumps(el, indent=4, sort_keys=True))
                print("\n")


def gcal_event_sample(num=1):
    # Set the timezone to match the timezone of your Google Calendar
    timezone = pytz.timezone(nt.TIMEZONE)

    # Get the current date with the correct timezone
    now = datetime.now(timezone)

    # Set timeMin and timeMax to cover the entire current day
    timeMin = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    timeMax = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

    # Fetch all calendar IDs
    calendars_result = gt.service.calendarList().list().execute()
    calendars = calendars_result.get("items", [])

    # Iterate over all calendars and fetch events
    all_events = []
    for calendar in calendars:
        calendar_id = calendar["id"]
        events_result = (
            gt.service.events()
            .list(calendarId=calendar_id, timeMin=timeMin, timeMax=timeMax)
            .execute()
        )
        events = events_result.get("items", [])
        all_events.extend(events[:num])  # Add the first 'num' events from each calendar

    # Process the collected events
    for event in all_events:
        print(json.dumps(event, indent=4))


if __name__ == "__main__":
    notion_event_sample()
    gcal_event_sample()
