import logging
import json
import os
import sys
import time
import pytz
from datetime import datetime, timedelta, date
from pathlib import Path

# Local application/library specific imports
import notion_token
import gcal_token


# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = CURRENT_DIR / "../token/notion_setting.json"

# Logging setup
logging.basicConfig(level=logging.INFO)

# Initialize Notion and Google tokens
nt = notion_token.Notion()
gt = gcal_token.Google()

# Load Notion settings
with open(NOTION_SETTINGS_PATH, "r") as file:
    data = json.load(file)


def get_all_gcal_eventid():
    """Retrieve all events from Google Calendar."""
    timezone = pytz.timezone(
        nt.TIMEZONE
    )  # Set the timezone to match the timezone of your Google Calendar

    # Calculate the start and end dates for the event range
    after_date = datetime.now(timezone) - timedelta(days=data["goback_days"])
    before_date = datetime.now(timezone) + timedelta(days=data["goforward_days"])

    try:
        events = []
        for cal_id in nt.GCAL_DIC.values():
            response = (
                gt.service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=after_date.isoformat(),  # ISO format for Google Calendar API
                    timeMax=before_date.isoformat(),
                )
                .execute()
            )
            if response['items'] != []:
                events.extend(response.get("items", []))
        return events
    except Exception as e:
        logging.error(f"Error retrieving Google Calendar events: {e}")
        return []


def DateTimeIntoNotionFormat(datetime_obj):
    """Format a datetime object for Notion."""
    return datetime_obj.strftime(f"%Y-%m-%dT%H:%M:%S{nt.TIMECODE}")


def makeTaskURL(ending, urlRoot):
    """Create a Notion task URL from a task ID."""
    urlId = ending.replace("-", "")
    return urlRoot + urlId


def makeEventDescription(initiative, info, task_status):
    """Format the event description for Google Calendar."""
    parts = []
    if initiative:
        parts.append(f"Initiative: {initiative}")
    if info:
        parts.append(info)
    parts.append(f"Task Status: {task_status}")
    return " \n".join(parts)


def makeCalEvent(
    exist_eventId,
    eventName,
    eventDescription,
    eventlocation,
    eventStartTime,
    eventEndTime,
    newCalId,
    oldCalId,
    sourceURL,
    skip=0,
):
    """Create or update a calendar event."""
    print("Convert Notion date type to Google calendar format: ", eventName)

    datetime_type = 0

    # Case 1: one-day allday event
    # Would you like to convert notion's allday event to GCal event with default of 8 am - 9 am?
    if (
        eventStartTime.hour == 0
        and eventStartTime.minute == 0
        and eventEndTime == eventStartTime
    ):
        # Yes
        if nt.ALLDAY_OPTION == 1:
            datetime_type = 1  # mark as datetime format
            eventStartTime = datetime.combine(
                eventStartTime, datetime.min.time()
            ) + timedelta(hours=nt.DEFAULT_EVENT_START)
            eventEndTime = eventStartTime + timedelta(minutes=nt.DEFAULT_EVENT_LENGTH)
        # No
        else:
            eventEndTime = eventEndTime + timedelta(days=1)
    # Case 2: cross-day allday event
    elif (
        eventStartTime.hour == 0
        and eventStartTime.minute == 0
        and eventEndTime.hour == 0
        and eventEndTime.minute == 0
        and eventStartTime != eventEndTime
    ):
        eventEndTime = eventEndTime + timedelta(days=1)
    # Case 3: Not allday event
    else:
        datetime_type = 1  # mark as datetime format
        # Start time == end time or NO end time
        if eventEndTime == eventStartTime or eventEndTime == None:
            eventStartTime = eventStartTime
            eventEndTime = eventStartTime + timedelta(minutes=nt.DEFAULT_EVENT_LENGTH)
        # if you give a specific start time to the event
        else:
            eventStartTime = eventStartTime
            eventEndTime = eventEndTime

    # write into Event: date or datetime
    if skip == 1:  # can skip some information if you want to
        event = {
            "summary": eventName,
            "location": eventlocation,
            "description": eventDescription,
            "start": {
                "dateTime": eventStartTime.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": nt.TIMEZONE,
            },
            "end": {
                "dateTime": eventEndTime.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": nt.TIMEZONE,
            },
            "source": {
                "title": "Notion Link",
                "url": sourceURL,
            },
        }
    else:
        if datetime_type == 1:
            event = {
                "summary": eventName,
                "location": eventlocation,
                "description": eventDescription,
                "start": {
                    "dateTime": eventStartTime.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": nt.TIMEZONE,
                },
                "end": {
                    "dateTime": eventEndTime.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": nt.TIMEZONE,
                },
                "source": {
                    "title": "Notion Link",
                    "url": sourceURL,
                },
            }
        else:
            event = {
                "summary": eventName,
                "location": eventlocation,
                "description": eventDescription,
                "start": {
                    "date": eventStartTime.strftime("%Y-%m-%d"),
                    "timeZone": nt.TIMEZONE,
                },
                "end": {
                    "date": eventEndTime.strftime("%Y-%m-%d"),
                    "timeZone": nt.TIMEZONE,
                },
                "source": {
                    "title": "Notion Link",
                    "url": sourceURL,
                },
            }

    if exist_eventId == "":
        x = gt.service.events().insert(calendarId=newCalId, body=event).execute()
    else:
        if newCalId == oldCalId:
            x = (
                gt.service.events()
                .update(calendarId=newCalId, eventId=exist_eventId, body=event)
                .execute()
            )
        else:  # When we have to move the event to a new calendar. We must move the event over to the new calendar and then update the information on the event
            print(
                f"Move {eventName} from {nt.GCAL_DIC_KEY_TO_VALUE[oldCalId]} Cal to {nt.GCAL_DIC_KEY_TO_VALUE[newCalId]} Cal"
            )
            print("\n")
            # move
            x = (
                gt.service.events()
                .move(calendarId=oldCalId, eventId=exist_eventId, destination=newCalId)
                .execute()
            )
            # update
            x = (
                gt.service.events()
                .update(calendarId=newCalId, eventId=exist_eventId, body=event)
                .execute()
            )
    return x["id"]


def queryGCalId(id, num=300):
    """Make a list of Google Calendar event IDs."""
    x = (
        gt.service.events()
        .list(
            calendarId=id,
            maxResults=num,
            timeMin=nt.GOOGLE_TIMEMIN,
            timeMax=nt.GOOGLE_TIMEMAX,
        )
        .execute()
    )
    return x


def deleteEvent():
    """Delete Google Calendar events."""
    print("\n")
    print("-------- Deletion | Done? == True in Notion, delete the GCal event --------")
    resultList = queryNotionEvent_delete()

    print(resultList)
    if len(resultList) > 0:
        for i, el in enumerate(resultList):
            # make sure that"s what you want
            summary = el["properties"]["Task Name"]["title"][0]["text"]["content"]
            pageId = el["id"]
            calendarID = nt.GCAL_DIC[
                el["properties"][nt.CURRENT_CALENDAR_NAME_NOTION_NAME]["select"]["name"]
            ]
            try:
                eventId = el["properties"][nt.GCALEVENTID_NOTION_NAME]["rich_text"][0][
                    "text"
                ]["content"]
            except Exception as e:
                print(
                    f"{summary} does not have event ID. Make sure that it exists in Notion"
                )
                print(e)
                sys.exit()
            print(f"{i}th processing GCal Event {summary}, EventID {eventId}")

            try:  # delete Gcal event
                gt.service.events().delete(
                    calendarId=calendarID, eventId=eventId
                ).execute()
                print(f"{i}th Deleting GCal Event {summary}, EventID {eventId}")
            except:
                continue

            # delete google event id and Cal id in Notion
            deleteGInfo(pageId)
    else:
        print("---------------------- No deleted the GCal event ----------------------")


# Example usage
if __name__ == "__main__":
    # Get all Google Calendar events
    gcal_events = get_all_gcal_eventid()
    for event in gcal_events:
        print(event)  # Process events as needed

    # Example event data (replace with actual data)
    event_data = {
        "exist_eventId": "",
        "eventName": "Meeting with Team",
        "eventDescription": "Discuss project updates",
        "eventLocation": "Virtual Meeting",
        "eventStartTime": datetime.now(),
        "eventEndTime": datetime.now() + timedelta(hours=1),
        "newCalId": "your_calendar_id",  # Replace with your calendar ID
        "event": {
            # Event details
        },
    }

    # Create or update an event
    event_id = create_or_update_calendar_event(event_data)
    if event_id:
        print(f"Event created/updated with ID: {event_id}")
