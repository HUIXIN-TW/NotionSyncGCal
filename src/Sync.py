import os
import sys
import json
import logging
from datetime import datetime, timedelta

from gcal_services import (
    get_all_gcal_eventid,
    DateTimeIntoNotionFormat,
    makeCalEvent,
    makeTaskURL,
    makeEventDescription,
    queryGCalId,
    deleteEvent,
)
from notion_services import (
    notion_time,
    get_all_notion_eventid,
    queryNotionEvent_all,
    queryNotionEvent_notion,
    queryNotionEvent_page,
    queryNotionEvent_gcal,
    queryNotionEvent_delete,
    updateGStatus,
    updateDefaultCal,
    updateCal,
    deleteGInfo,
    create_page,
    update_page_all,
    update_page_time,
)

import gcal_token
import notion_token
import sample_event


try:
    nt = notion_token.Notion()
    gt = gcal_token.Google()
    print(f"--- {nt} ---")
    print("--- Notion activated ---")
    print(f"--- {gt.service} ---")
    print("--- Google activated ---")
    print("\n")
    print("################################## START ##################################")
    print("###########################################################################")
    print(
        f"---  sync | After {nt.AFTER_DATE} Included, Before {nt.BEFORE_DATE} Not Included  ---"
    )
except Exception as e:
    raise e


class NotionToGCal:
    def __init__(self, action="UPDATE", updateEverything=True):
        self.action = action
        self.updateEverything = updateEverything
        self.all_notion_gCal_Ids, self.all_notion_gCal_Ids_pageid = None, None
        self.calItems = None
        self.calIds = []
        self.resultList = []
        self.resultLists = []

    @staticmethod
    def query_database(updateEverything):
        if updateEverything:
            return queryNotionEvent_notion()
        else:
            return queryNotionEvent_all()

    @staticmethod
    def extract_event_details(el):
        event_details = {}

        # set icone and task name
        try:
            event_icon = el["properties"][nt.COMPLETEICON_NOTION_NAME]["formula"][
                "string"
            ]
            event_name = el["properties"][nt.TASK_NOTION_NAME]["title"][0]["text"][
                "content"
            ]
            event = event_icon + event_name
            event_details["event"] = event
        except:
            event_icon = "❓"
            event_name = el["properties"][nt.TASK_NOTION_NAME]["title"][0]["text"][
                "content"
            ]
            event = event_icon + event_name
            event_details["event"] = event

        # set start and end date
        try:
            event_start_date = el["properties"][nt.DATE_NOTION_NAME]["date"]["start"]
            event_details["start_date"] = event_start_date
        except Exception as e:
            event_details["start_date"] = None
            print(f"Error getting start date: {e}")
        try:
            event_end_date = el["properties"][nt.DATE_NOTION_NAME]["date"]["end"]
            event_details["end_date"] = event_end_date
        except Exception as e:
            event_end_date = el["properties"][nt.DATE_NOTION_NAME]["date"]["start"]
            event_details["end_date"] = event_end_date
            print(f"Error getting end date: {e}")
        return event_details

    @staticmethod
    def extract_initiative_details(el):
        try:
            # multiple choice
            if len(el["properties"][nt.INITIATIVE_NOTION_NAME]["multi_select"]) > 1:
                first_initiative = el["properties"][nt.INITIATIVE_NOTION_NAME][
                    "multi_select"
                ][0]["name"]
                mul_initiative = first_initiative + "...etc."
                return mul_initiative
            # single choice
            else:
                return el["properties"][nt.INITIATIVE_NOTION_NAME]["multi_select"][0][
                    "name"
                ]
        except:
            return ""

    @staticmethod
    def extract_extra_info(el):
        try:
            extra_info = el["properties"][nt.EXTRAINFO_NOTION_NAME]["rich_text"][0][
                "text"
            ]["content"]
        except:
            extra_info = ""
        return extra_info

    @staticmethod
    def extract_task_status(el):
        try:
            task_status = el["properties"][nt.STATUS_NOTION_NAME]["select"]["name"]
        except:
            task_status = ""
        return task_status

    @staticmethod
    def extract_url_list(el):
        try:
            url = makeTaskURL(el["id"], nt.URLROOT)
        except Exception as e:
            url = ""
            print(f"Error extracting URL: {e}")
        return url

    @staticmethod
    def extract_calendar_list(el):
        try:
            calendar_name = el["properties"][nt.CALENDAR_NOTION_NAME]["select"]["name"]
            calendar_list = nt.GCAL_DIC.get(calendar_name, nt.GCAL_DEFAULT_ID)
        except KeyError:
            calendar_list = nt.GCAL_DEFAULT_ID
        except Exception as e:
            print(f"Error extracting calendar list: {e}")
            calendar_list = nt.GCAL_DEFAULT_ID
        return calendar_list

    @staticmethod
    def extract_location(el):
        try:
            location = el["properties"][nt.LOCATION_NOTION_NAME]["rich_text"][0][
                "text"
            ]["content"]
        except:
            location = ""
        return location

    @staticmethod
    def update_gstatus(pageId):
        try:
            updateGStatus(pageId)
        except Exception as e:
            print(f"Error updating GStatus for page {pageId}: {e}")

    @staticmethod
    def make_cal_event(args):
        try:
            cal_event_id = makeCalEvent(*args)
            return cal_event_id
        except Exception as e:
            print(f"Error creating calendar event: {e}")
            return None

    @staticmethod
    def update_cal(pageId, calEventId, calendarList):
        try:
            updateCal(pageId, calEventId, calendarList)
        except Exception as e:
            print(f"Error updating calendar for page {pageId}: {e}")

    @staticmethod
    def update_default_cal(pageId, calEventId, calendarList):
        try:
            updateDefaultCal(pageId, calEventId, calendarList)
        except Exception as e:
            print(f"Error updating default calendar for page {pageId}: {e}")

    def main(self):
        self.resultList = self.query_database(self.updateEverything)

        if self.resultList:
            n = len(self.resultList)
            logging.info(
                f"---- {n} EVENTS: RUNNING NOTIONSYNC NOW | Change in Notion to Gcalendar ----"
            )

            for i, el in enumerate(self.resultList):
                logging.info(
                    f"---- {i} th Result ready to be updated to google calendar ----"
                )

                event_details = self.extract_event_details(el)
                initiative_details = self.extract_initiative_details(el)
                extra_info = self.extract_extra_info(el)
                task_status = self.extract_task_status(el)
                url_list = self.extract_url_list(el)
                calendar_list = self.extract_calendar_list(el)
                location = self.extract_location(el)

                # Now we will use the extracted details to create or update events on Google Calendar
                event_description = makeEventDescription(
                    initiative_details, extra_info, task_status
                )

                # Get existing event ID from Notion properties, if any
                try:
                    existing_event_id = el["properties"][nt.GCALEVENTID_NOTION_NAME][
                        "rich_text"
                    ][0]["text"]["content"]
                except:
                    existing_event_id = ""

                # Get current calendar ID from Notion properties
                try:
                    current_calendar_id = el["properties"][
                        nt.CURRENT_CALENDAR_ID_NOTION_NAME
                    ]["rich_text"][0]["text"]["content"]
                except:
                    current_calendar_id = ""

                # Get page ID
                page_id = el["id"]

                # Update the GCal status on Notion first
                self.update_gstatus(page_id)

                # Check for subscription calendar
                if "@import.calendar.google.com" in current_calendar_id:
                    calendar_name = el["properties"][nt.CALENDAR_NOTION_NAME]["select"][
                        "name"
                    ]
                    logging.info(
                        f"---- {calendar_name} is a subscription which can't be edited ----"
                    )
                    continue

                # Create or update event on Google Calendar
                try:
                    start_date = datetime.strptime(
                        event_details["start_date"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                    end_date = datetime.strptime(
                        event_details["end_date"], "%Y-%m-%dT%H:%M:%S.%f%z"
                    )
                except:
                    start_date = datetime.strptime(
                        event_details["start_date"], "%Y-%m-%d"
                    )
                    end_date = datetime.strptime(event_details["end_date"], "%Y-%m-%d")

                cal_event_id = self.make_cal_event(
                    [
                        existing_event_id,
                        event_details["event"],
                        event_description,
                        location,
                        start_date,
                        end_date,
                        calendar_list,
                        current_calendar_id,
                        url_list,
                    ]
                )

                # If the calendar list ID matches the default, update the default calendar on Notion
                if calendar_list == nt.GCAL_DEFAULT_ID:
                    self.update_default_cal(page_id, cal_event_id, calendar_list)
                else:  # Regular update
                    self.update_cal(page_id, cal_event_id, calendar_list)

        else:
            logging.info(
                "Result List is empty. Nothing new from Notion to be added to GCal"
            )


class GCalToNotion:
    def __init__(self, action="UPDATE_TIME_CREATE_NEW_BY_GOOGLE"):
        self.action = action
        (
            self.all_notion_gCal_Ids,
            self.all_notion_gCal_Ids_pageid,
        ) = get_all_notion_eventid("gcal_to_notion")
        self.calItems = get_all_gcal_eventid()
        self.process_calendar_items()

    def process_calendar_items(self):
        cal_data = [self.extract_calendar_data(item) for item in self.calItems]
        for item in cal_data:
            print("Calendar Data Item:", item['summary'])
        self.compare_and_update_calendars(cal_data)

    @staticmethod
    def extract_calendar_data(calItem):
        data = {}
        data["id"] = calItem.get("id", "")
        data["summary"] = calItem.get("summary", "")

        organizer = calItem.get("organizer", {})
        data["organizer_email"] = organizer.get("email", "")
        data["organizer_display_name"] = organizer.get(
            "displayName", nt.GCAL_DIC_KEY_TO_VALUE.get(data["organizer_email"], "")
        )

        # Extracting start date and time
        start = calItem.get("start", {})
        if "dateTime" in start:
            data["start_date_time"] = datetime.strptime(
                start["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S"
            )
        elif "date" in start:
            date = datetime.strptime(start["date"], "%Y-%m-%d")
            data["start_date_time"] = datetime(date.year, date.month, date.day, 0, 0, 0)
        else:
            data["start_date_time"] = None

        # Extracting end date and time
        end = calItem.get("end", {})
        if "dateTime" in end:
            data["end_date_time"] = datetime.strptime(
                end["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S"
            )
        elif "date" in end:
            date = datetime.strptime(end["date"], "%Y-%m-%d")
            data["end_date_time"] = datetime(date.year, date.month, date.day, 0, 0, 0)
        else:
            data["end_date_time"] = None

        # Extracting description and location
        description = calItem.get("description", "")
        location = calItem.get("location", "")
        if description and location:
            data["description"] = f"{description}\nLocation: {location}"
        else:
            data["description"] = description or location or " "

        data["location"] = location if location else "No Location Info"

        return data

    def compare_and_update_calendars(self, cal_data):
        for data in cal_data:
            calStartDate, calEndDate = self.format_dates(
                data["start_date_time"], data["end_date_time"]
            )

            if data["id"] in self.all_notion_gCal_Ids:
                pageid = self.all_notion_gCal_Ids_pageid[data["id"]]
                if self.action == "OVERWRITE_BY_GOOGLE":
                    update_page_all(
                        pageid,
                        data["summary"],
                        calStartDate,
                        calEndDate,
                        data["description"],
                        data["location"],
                        data["id"],
                        data["organizer_email"],
                        nt.GCAL_DIC_KEY_TO_VALUE[data["organizer_email"]],
                    )
                elif (
                    self.action == "UPDATE_TIME_CREATE_NEW_BY_GOOGLE"
                ):  # Default action
                    update_page_time(
                        pageid,
                        data["summary"],
                        calStartDate,
                        calEndDate,
                        data["organizer_email"],
                        nt.GCAL_DIC_KEY_TO_VALUE[data["organizer_email"]],
                    )
            else:  # Create new event in Notion
                create_page(
                    data["summary"],
                    calStartDate,
                    calEndDate,
                    data["description"],
                    data["location"],
                    data["id"],
                    data["organizer_email"],
                    nt.GCAL_DIC_KEY_TO_VALUE[data["organizer_email"]],
                )

    def format_dates(self, start_date_time, end_date_time):
        # Logic to format dates in the required format
        if start_date_time == end_date_time - timedelta(days=1):
            calStartDate = start_date_time.strftime("%Y-%m-%d")
            calEndDate = None
        elif (
            start_date_time.hour == 0
            and start_date_time.minute == 0
            and end_date_time.hour == 0
            and end_date_time.minute == 0
        ):
            calStartDate = start_date_time.strftime("%Y-%m-%d")
            calEndDate = (end_date_time - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            calStartDate = DateTimeIntoNotionFormat(start_date_time)
            calEndDate = DateTimeIntoNotionFormat(end_date_time)

        return calStartDate, calEndDate
