from datetime import timedelta
from dateutil.parser import isoparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from notion.notion_properties import get_property


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


GCAL_PAGE_SIZE = 2500
MAX_GCAL_PAGES_PER_CALENDAR = 100
MAX_GCAL_EVENTS_PER_CALENDAR = 500


class GoogleService:

    def __init__(self, user_setting, google_token, logger):
        self.logger = logger
        self.notion_setting = user_setting
        self.notion_page_property = user_setting["page_property"]
        try:
            self.service = build("calendar", "v3", credentials=google_token.credentials)
            self.logger.debug("Google Calendar service initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing Google service: {e}")
            raise

    def configure_calendar_mappings(self):
        """Resolve mutable Calendar display names from persisted provider IDs."""
        requested_ids = set(self.notion_setting["calendar_ids"])
        calendars_by_id = {}
        page_token = None
        while True:
            response = self.service.calendarList().list(pageToken=page_token).execute()
            for calendar in response.get("items", []):
                calendar_id = calendar.get("id")
                if calendar_id in requested_ids:
                    calendars_by_id[calendar_id] = calendar
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        missing = sorted(requested_ids - calendars_by_id.keys())
        if missing:
            raise SettingError(f"Configured Google Calendars are not accessible: {missing}")

        name_to_id = {}
        for calendar_id in sorted(requested_ids):
            calendar = calendars_by_id[calendar_id]
            name = calendar.get("summaryOverride") or calendar.get("summary") or calendar_id
            if name in name_to_id and name_to_id[name] != calendar_id:
                raise SettingError(f"Configured Google Calendars have a duplicate display name: {name}")
            name_to_id[name] = calendar_id
        self.notion_setting["gcal_name_dict"] = name_to_id
        self.notion_setting["gcal_id_dict"] = {calendar_id: name for name, calendar_id in name_to_id.items()}
        return name_to_id

    def test_connection(self):
        """Quick sanity check to confirm credentials are valid and API reachable."""
        try:
            self.service.calendarList().list(maxResults=1).execute()
            self.logger.debug("Google Calendar connection test passed.")
            return True
        except HttpError as e:
            self.logger.error(f"Google API error: {e}. Please click 'view settings' and re-authorize")
            return False
        except Exception as e:
            self.logger.error(f"Google Calendar Connection test failed: {e}")
            return False

    def get_gcal_event(self):
        # Calculate the start and end dates for the event range
        try:
            events = []

            for cal_id in self.notion_setting["calendar_ids"]:
                page_token = None
                seen_page_tokens = set()
                page_count = 0
                cal_fetched = 0
                cal_skipped = 0

                while True:
                    page_count += 1

                    if page_count > MAX_GCAL_PAGES_PER_CALENDAR:
                        raise RuntimeError(
                            f"Exceeded Google Calendar pagination limit for calendar ID {cal_id}: "
                            f"{MAX_GCAL_PAGES_PER_CALENDAR} pages"
                        )

                    if page_token:
                        if page_token in seen_page_tokens:
                            raise RuntimeError(f"Repeated Google Calendar page token detected for calendar ID {cal_id}")
                        seen_page_tokens.add(page_token)

                    params = {
                        "calendarId": cal_id,
                        "timeMin": self.notion_setting["google_timemin"],
                        "timeMax": self.notion_setting["google_timemax"],
                        "singleEvents": True,
                        "orderBy": "startTime",
                        "maxResults": GCAL_PAGE_SIZE,
                    }

                    if page_token:
                        params["pageToken"] = page_token

                    response = self.service.events().list(**params).execute()

                    for raw_item in response.get("items", []):
                        item = {**raw_item, "_notica_calendar_id": cal_id}
                        if item.get("status") == "cancelled":
                            self.logger.debug(
                                f"Skipping cancelled recurring exception: id={item.get('id')} "
                                f"originalStartTime={item.get('originalStartTime', {})}"
                            )
                            cal_skipped += 1
                            continue

                        if not item.get("start"):
                            self.logger.warning(
                                "Skipping event with missing start field: id=%s",
                                item.get("id"),
                            )
                            cal_skipped += 1
                            continue
                        if cal_fetched >= MAX_GCAL_EVENTS_PER_CALENDAR:
                            raise RuntimeError(
                                f"Exceeded Google Calendar event limit for calendar ID {cal_id}: "
                                f"{MAX_GCAL_EVENTS_PER_CALENDAR} events"
                            )
                        events.append(item)
                        cal_fetched += 1

                    page_token = response.get("nextPageToken")
                    if not page_token:
                        break

                self.logger.debug(
                    f"Retrieved {cal_fetched} valid events from calendar ID {cal_id} "
                    f"({cal_skipped} skipped, {page_count} pages)"
                )

            self.logger.debug(f"Total events retrieved: {len(events)}")
            return events

        except RefreshError as e:
            self.logger.error(f"RefreshError: {e}")
            raise

        except Exception:
            self.logger.exception("Error retrieving Google Calendar events")
            raise

    def update_gcal_event(self, notion_task, existing_gcal_cal_id, existing_gcal_event_id):
        event = self.make_event_body(notion_task)
        self.service.events().patch(
            calendarId=existing_gcal_cal_id, eventId=existing_gcal_event_id, body=event
        ).execute()

    def create_gcal_event(self, notion_task, new_gcal_calendar_id):
        if new_gcal_calendar_id is None:
            raise SettingError("A Notion task must select one configured Google Calendar.")
        event = self.make_event_body(notion_task)
        gcal_event = self.service.events().insert(calendarId=new_gcal_calendar_id, body=event).execute()
        # get the event id and update the notion task by query page id
        event_id = gcal_event.get("id")
        return event_id

    def move_and_update_gcal_event(
        self,
        notion_task,
        existing_gcal_event_id,
        new_gcal_calendar_id,
        existing_gcal_cal_id,
    ):
        self.service.events().move(
            calendarId=existing_gcal_cal_id,
            eventId=existing_gcal_event_id,
            destination=new_gcal_calendar_id,
        ).execute()
        self.update_gcal_event(notion_task, new_gcal_calendar_id, existing_gcal_event_id)

    def delete_gcal_event(self, gcal_calendar_id, gcal_event_id):
        try:
            self.service.events().delete(calendarId=gcal_calendar_id, eventId=gcal_event_id).execute()
            self.logger.info(f"Successfully deleted event with ID: {gcal_event_id}")
            return True
        except HttpError as e:
            status_code = getattr(getattr(e, "resp", None), "status", None)
            if status_code in (404, 410):
                self.logger.warning(
                    "Google Calendar event_id=%s was already absent (status=%s); treating delete as converged.",
                    gcal_event_id,
                    status_code,
                )
                return True
            self.logger.error(f"An error occurred while deleting event with ID: {gcal_event_id}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"An error occurred while deleting event with ID: {gcal_event_id}: {e}")
            raise

    def make_event_body(self, notion_task):
        # set icone and task name
        properties = notion_task.get("properties", {})
        event_icon = (
            get_property(properties, self.notion_page_property.get("CompleteIcon_Notion_Name"))
            .get("formula", {})
            .get("string", "")
        )
        task_items = get_property(properties, self.notion_page_property["Task_Notion_Name"]).get("title", [])
        event_name = task_items[0].get("plain_text", "") if task_items else ""
        event_summary = event_icon + event_name

        # set start and end date
        # notion datetime format is "2024-05-27T19:00:00.000+08:00":
        #   case1: with end datetime (using) or
        #   case2: without end datetime (use start datetime + 1 hour)
        # notion date format is "2024-05-26"
        #   case1: with end date (using end date + 1 day) or
        #   case2: without end date (use start date + 1 day)
        # to_utc(event_start_date).strftime("%Y-%m-%dT%H:%M:%S")
        # to_utc(event_start_date).strftime("%Y-%m-%d")
        date_property = get_property(properties, self.notion_page_property["Date_Notion_Name"])
        notion_task_start_date = (date_property.get("date") or {}).get("start", "")
        notion_task_end_date = (date_property.get("date") or {}).get("end", "")
        # Adjust and convert dates to UTC
        event_start_date, event_end_date = self.adjust_notion_dates(notion_task_start_date, notion_task_end_date)

        # set location
        try:
            event_location = (
                get_property(properties, self.notion_page_property.get("Location_Notion_Name"))
                .get("place", {})
                .get("address", "")
            )
        except Exception as e:
            self.logger.info(f"Getting location: {e}. Using empty string.")
            event_location = ""

        # set description
        try:
            rich_text = get_property(properties, self.notion_page_property.get("ExtraInfo_Notion_Name")).get(
                "rich_text", []
            )
            event_description = rich_text[0].get("plain_text", "") if rich_text else ""
        except Exception as e:
            self.logger.info(f"Getting description: {e}. Using empty string.")
            event_description = ""

        # set url
        event_source_url = notion_task.get("url", "")

        timezone = self.notion_setting["timezone"]
        if "T" in event_start_date:
            event = {
                "summary": event_summary,
                "location": event_location,
                "description": event_description,
                "start": {
                    "dateTime": event_start_date,
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": event_end_date,
                    "timeZone": timezone,
                },
                "source": {
                    "title": "Notion Link",
                    "url": event_source_url,
                },
            }
        else:
            event = {
                "summary": event_summary,
                "location": event_location,
                "description": event_description,
                "start": {"date": event_start_date},
                "end": {"date": event_end_date},
                "source": {
                    "title": "Notion Link",
                    "url": event_source_url,
                },
            }
        return event

    def adjust_notion_dates(self, start_date_str, end_date_str=None):
        """
        TODO: Consider Different Timezones
        Adjust Notion date or datetime formats and convert them to UTC.
        """
        start_date = isoparse(start_date_str)
        if end_date_str:
            end_date = isoparse(end_date_str)
        else:
            end_date = start_date

        if "T" in start_date_str and end_date == start_date:  # datetime format
            end_date = start_date + timedelta(minutes=int(self.notion_setting["default_event_length"]))
        elif "T" not in start_date_str:  # date format: Google Calendar end date is exclusive, always add 1 day
            end_date = end_date + timedelta(days=1)

        if "T" in start_date_str:
            start_date_str = start_date.strftime("%Y-%m-%dT%H:%M:%S%z")
            end_date_str = end_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            start_date_str = start_date.strftime("%Y-%m-%d")
            end_date_str = end_date.strftime("%Y-%m-%d")
        return start_date_str, end_date_str
