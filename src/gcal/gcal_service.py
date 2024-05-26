import logging
import json
import os
import sys
import time
import pytz
from datetime import datetime, timedelta, date
from pathlib import Path

# Ensure the project root is in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if PROJECT_ROOT not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# Local application/library specific imports
from notion import notion_token
from . import gcal_token

# Configure logging
logging.basicConfig(filename="google_services.log", level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the absolute path to the current directory
logger.info(f"Current directory: {CURRENT_DIR}")

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = (CURRENT_DIR / "../../token/notion_setting.json").resolve()
CLIENT_SECRET_PATH = (CURRENT_DIR / "../../token/client_secret.json").resolve()
CREDENTIALS_PATH = (CURRENT_DIR / "../../token/token.pkl").resolve()

# Initialize Notion and Google tokens
nt = notion_token.Notion()
gt = gcal_token.Google()


def get_gcal_event():
    """
    Retrieve all events from Google Calendar within a specified date range.

    Returns:
        List[Dict]: A list of event dictionaries retrieved from Google Calendar.
    """
    timezone = pytz.timezone(nt.TIMEZONE)

    # Calculate the start and end dates for the event range
    try:
        events = []
        for cal_id in nt.GCAL_DIC.values():
            response = (
                gt.service.events()
                .list(
                    calendarId=cal_id,
                    timeMin=nt.GOOGLE_TIMEMIN,
                    timeMax=nt.GOOGLE_TIMEMAX,
                )
                .execute()
            )

            if response.get("items"):
                events.extend(response["items"])
            logger.info(
                f"Retrieved {len(response.get('items', []))} events from calendar ID {cal_id}"
            )

        logger.info(f"Total events retrieved: {len(events)}")
        return events
    except Exception as e:
        logger.error(f"Error retrieving Google Calendar events: {e}", exc_info=True)
        return []


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


def update_gcal_event(gcal_event, notion_task):
    return "Calling update_gcal_event"
    print(gcal_event, notion_task)


def create_gcal_event(notion_task):
    return "Calling create_gcal_event"
    print(notion_task)


def delete_gcal_event(gcal_event):
    return "Calling delete_gcal_event"
    print(gcal_event)

# Example usage
if __name__ == "__main__":
    # Ensure the directory exists
    Path("logs").mkdir(parents=True, exist_ok=True)

    # Check if the file exists and create it if not
    log_path = Path("logs/get_gcal_event.json")
    if not log_path.exists():
        log_path.touch()

    # Open the file in write mode and dump JSON data
    with log_path.open("w") as output:
        json.dump(get_gcal_event(), output, indent=4)


# class NotionToGCal:
#     @staticmethod
#     def extract_event_details(el):
#         event_details = {}

#         # set icone and task name
#         try:
#             event_icon = el["properties"][nt.COMPLETEICON_NOTION_NAME]["formula"][
#                 "string"
#             ]
#             event_name = el["properties"][nt.TASK_NOTION_NAME]["title"][0]["text"][
#                 "content"
#             ]
#             event = event_icon + event_name
#             event_details["event"] = event
#         except:
#             event_icon = "❓"
#             event_name = el["properties"][nt.TASK_NOTION_NAME]["title"][0]["text"][
#                 "content"
#             ]
#             event = event_icon + event_name
#             event_details["event"] = event

#         # set start and end date
#         try:
#             event_start_date = el["properties"][nt.DATE_NOTION_NAME]["date"]["start"]
#             event_details["start_date"] = event_start_date
#         except Exception as e:
#             event_details["start_date"] = None
#             print(f"Error getting start date: {e}")
#         try:
#             event_end_date = el["properties"][nt.DATE_NOTION_NAME]["date"]["end"]
#             event_details["end_date"] = event_end_date
#         except Exception as e:
#             event_end_date = el["properties"][nt.DATE_NOTION_NAME]["date"]["start"]
#             event_details["end_date"] = event_end_date
#             print(f"Error getting end date: {e}")
#         return event_details

#     @staticmethod
#     def extract_initiative_details(el):
#         try:
#             # multiple choice
#             if len(el["properties"][nt.INITIATIVE_NOTION_NAME]["multi_select"]) > 1:
#                 first_initiative = el["properties"][nt.INITIATIVE_NOTION_NAME][
#                     "multi_select"
#                 ][0]["name"]
#                 mul_initiative = first_initiative + "...etc."
#                 return mul_initiative
#             # single choice
#             else:
#                 return el["properties"][nt.INITIATIVE_NOTION_NAME]["multi_select"][0][
#                     "name"
#                 ]
#         except:
#             return ""

#     @staticmethod
#     def extract_extra_info(el):
#         try:
#             extra_info = el["properties"][nt.EXTRAINFO_NOTION_NAME]["rich_text"][0][
#                 "text"
#             ]["content"]
#         except:
#             extra_info = ""
#         return extra_info

#     @staticmethod
#     def extract_task_status(el):
#         try:
#             task_status = el["properties"][nt.STATUS_NOTION_NAME]["status"]["name"]
#         except:
#             task_status = ""
#         return task_status

#     @staticmethod
#     def extract_url_list(el):
#         try:
#             url = makeTaskURL(el["id"], nt.URLROOT)
#         except Exception as e:
#             url = ""
#             print(f"Error extracting URL: {e}")
#         return url

#     @staticmethod
#     def extract_calendar_list(el):
#         try:
#             calendar_name = el["properties"][nt.CURRENT_CALENDAR_NAME_NOTION_NAME][
#                 "select"
#             ]["name"]
#             calendar_list = nt.GCAL_DIC.get(calendar_name, nt.GCAL_DEFAULT_ID)
#         except KeyError:
#             calendar_list = nt.GCAL_DEFAULT_ID
#         except Exception as e:
#             print(f"Error extracting calendar list: {e}")
#             calendar_list = nt.GCAL_DEFAULT_ID
#         return calendar_list

#     @staticmethod
#     def extract_location(el):
#         try:
#             location = el["properties"][nt.LOCATION_NOTION_NAME]["rich_text"][0][
#                 "text"
#             ]["content"]
#         except:
#             location = ""
#         return location

#     @staticmethod
#     def update_gstatus(pageId):
#         try:
#             updateGStatus(pageId)
#         except Exception as e:
#             print(f"Error updating GStatus for page {pageId}: {e}")

#     @staticmethod
#     def make_cal_event(args):
#         try:
#             cal_event_id = makeCalEvent(*args)
#             return cal_event_id
#         except Exception as e:
#             print(f"Error creating calendar event: {e}")
#             return None

#     @staticmethod
#     def update_cal(pageId, calEventId, calendarList):
#         try:
#             updateCal(pageId, calEventId, calendarList)
#         except Exception as e:
#             print(f"Error updating calendar for page {pageId}: {e}")

#     @staticmethod
#     def update_default_cal(pageId, calEventId, calendarList):
#         try:
#             updateDefaultCal(pageId, calEventId, calendarList)
#         except Exception as e:
#             print(f"Error updating default calendar for page {pageId}: {e}")

#     def main(self):
#         self.resultList = self.query_database(self.updateEverything)

#         if self.resultList:
#             n = len(self.resultList)
#             logging.info(
#                 f"---- {n} EVENTS: RUNNING NOTIONSYNC NOW | Change in Notion to Gcalendar ----"
#             )

#             for i, el in enumerate(self.resultList):
#                 logging.info(
#                     f"---- {i} th Result ready to be updated to google calendar ----"
#                 )

#                 event_details = self.extract_event_details(el)
#                 initiative_details = self.extract_initiative_details(el)
#                 extra_info = self.extract_extra_info(el)
#                 task_status = self.extract_task_status(el)
#                 url_list = self.extract_url_list(el)
#                 calendar_list = self.extract_calendar_list(el)
#                 location = self.extract_location(el)

#                 # Now we will use the extracted details to create or update events on Google Calendar
#                 event_description = makeEventDescription(
#                     initiative_details, extra_info, task_status
#                 )

#                 # Get existing event ID from Notion properties, if any
#                 try:
#                     existing_event_id = el["properties"][nt.GCALEVENTID_NOTION_NAME][
#                         "rich_text"
#                     ][0]["text"]["content"]
#                 except:
#                     existing_event_id = ""

#                 # Get current calendar ID from Notion properties
#                 try:
#                     current_calendar_id = el["properties"][
#                         nt.CURRENT_CALENDAR_ID_NOTION_NAME
#                     ]["rich_text"][0]["text"]["content"]
#                 except:
#                     current_calendar_id = ""

#                 # Get page ID
#                 page_id = el["id"]

#                 # Update the GCal status on Notion first
#                 self.update_gstatus(page_id)

#                 # Check for subscription calendar
#                 if "@import.calendar.google.com" in current_calendar_id:
#                     calendar_name = el["properties"][
#                         nt.CURRENT_CALENDAR_NAME_NOTION_NAME
#                     ]["select"]["name"]
#                     logging.info(
#                         f"---- {calendar_name} is a subscription which can't be edited ----"
#                     )
#                     continue

#                 # Create or update event on Google Calendar
#                 try:
#                     start_date = datetime.strptime(
#                         event_details["start_date"], "%Y-%m-%dT%H:%M:%S.%f%z"
#                     )
#                     end_date = datetime.strptime(
#                         event_details["end_date"], "%Y-%m-%dT%H:%M:%S.%f%z"
#                     )
#                 except:
#                     start_date = datetime.strptime(
#                         event_details["start_date"], "%Y-%m-%d"
#                     )
#                     end_date = datetime.strptime(event_details["end_date"], "%Y-%m-%d")

#                 cal_event_id = self.make_cal_event(
#                     [
#                         existing_event_id,
#                         event_details["event"],
#                         event_description,
#                         location,
#                         start_date,
#                         end_date,
#                         calendar_list,
#                         current_calendar_id,
#                         url_list,
#                     ]
#                 )

#                 # If the calendar list ID matches the default, update the default calendar on Notion
#                 if calendar_list == nt.GCAL_DEFAULT_ID:
#                     self.update_default_cal(page_id, cal_event_id, calendar_list)
#                 else:  # Regular update
#                     self.update_cal(page_id, cal_event_id, calendar_list)

#         else:
#             logging.info(
#                 "Result List is empty. Nothing new from Notion to be added to GCal"
#             )
