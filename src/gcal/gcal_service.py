from datetime import timedelta
from dateutil.parser import isoparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.exceptions import RefreshError
from notion.notion_properties import get_property
from sync.projection_identity import assert_projection_ownership


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


GCAL_PAGE_SIZE = 2500
MAX_GCAL_PAGES_PER_CALENDAR = 100
MAX_GCAL_EVENTS_PER_CALENDAR = 500


class GoogleService:

    def __init__(self, user_setting, google_token, logger, mutation_guard=None):
        self.logger = logger
        self.notion_setting = user_setting
        self.notion_page_property = user_setting["page_property"]
        self.calendar_id = user_setting["calendar_id"]
        self.mutation_guard = mutation_guard
        try:
            self.service = build("calendar", "v3", credentials=google_token.credentials)
            self.logger.debug("Google Calendar service initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing Google service: {e}")
            raise

    def validate_calendar_access(self):
        """Verify the configured provider target by immutable Calendar ID."""
        try:
            calendar = self.service.calendarList().get(calendarId=self.calendar_id).execute()
        except HttpError as exc:
            raise SettingError(
                f"Configured Google Calendar is not accessible: {self.calendar_id}"
            ) from exc
        if calendar.get("id") != self.calendar_id:
            raise SettingError("Google Calendar lookup returned an unexpected Calendar ID.")
        return True

    # Compatibility alias for older callers/tests while routing no longer uses names.
    def configure_calendar_mappings(self):
        return self.validate_calendar_access()

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

    def _assert_mutation_allowed(self):
        if self.mutation_guard is not None:
            self.mutation_guard()

    def get_projection_event(self, projection):
        event_id = projection["event_id"]
        try:
            event = (
                self.service.events()
                .get(calendarId=self.calendar_id, eventId=event_id)
                .execute()
            )
            assert_projection_ownership(event, projection)
            return event
        except HttpError as exc:
            status_code = getattr(getattr(exc, "resp", None), "status", None)
            if status_code in (404, 410):
                return None
            raise

    def get_gcal_event(self):
        """List only events attributed to this mapping; never scan a shared Calendar broadly."""
        events = []
        page_token = None
        page_count = 0
        mapping_id = self.notion_setting["mapping_id"]

        while True:
            page_count += 1
            if page_count > MAX_GCAL_PAGES_PER_CALENDAR:
                raise RuntimeError(
                    f"Exceeded Google Calendar pagination limit for mapping {mapping_id}: "
                    f"{MAX_GCAL_PAGES_PER_CALENDAR} pages"
                )

            params = {
                "calendarId": self.calendar_id,
                "timeMin": self.notion_setting["google_timemin"],
                "timeMax": self.notion_setting["google_timemax"],
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": GCAL_PAGE_SIZE,
                "privateExtendedProperty": [f"noticaMapping={mapping_id}"],
            }
            if page_token:
                params["pageToken"] = page_token

            response = self.service.events().list(**params).execute()
            for item in response.get("items", []):
                if item.get("status") == "cancelled" or not item.get("start"):
                    continue
                if len(events) >= MAX_GCAL_EVENTS_PER_CALENDAR:
                    raise RuntimeError(
                        f"Exceeded Google Calendar event limit for mapping {mapping_id}: "
                        f"{MAX_GCAL_EVENTS_PER_CALENDAR} events"
                    )
                events.append({**item, "_notica_calendar_id": self.calendar_id})

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return events

    def _projection_event_body(self, notion_task, projection, *, include_id=False):
        event = self.make_event_body(notion_task)
        event["extendedProperties"] = {"private": dict(projection["private"])}
        if include_id:
            event["id"] = projection["event_id"]
        return event

    def _patch_projection(self, notion_task, projection):
        self._assert_mutation_allowed()
        return (
            self.service.events()
            .patch(
                calendarId=self.calendar_id,
                eventId=projection["event_id"],
                body=self._projection_event_body(notion_task, projection),
            )
            .execute()
        )

    def upsert_projection(self, notion_task, projection):
        existing = self.get_projection_event(projection)
        if existing is not None:
            self._patch_projection(notion_task, projection)
            return projection["event_id"]

        self._assert_mutation_allowed()
        try:
            created = (
                self.service.events()
                .insert(
                    calendarId=self.calendar_id,
                    body=self._projection_event_body(
                        notion_task,
                        projection,
                        include_id=True,
                    ),
                )
                .execute()
            )
            assert_projection_ownership(created, projection)
            return projection["event_id"]
        except HttpError as exc:
            status_code = getattr(getattr(exc, "resp", None), "status", None)
            if status_code != 409:
                raise

            # Deterministic IDs turn a concurrent/retried create into a recoverable
            # ownership check instead of a second provider event.
            existing = self.get_projection_event(projection)
            if existing is None:
                raise
            self._patch_projection(notion_task, projection)
            return projection["event_id"]
        except Exception:
            # The insert may have reached Google even if the response was lost.
            # Read the deterministic ID back before surfacing a retryable error.
            recovered = self.get_projection_event(projection)
            if recovered is not None:
                return projection["event_id"]
            raise

    def delete_projection(self, projection):
        existing = self.get_projection_event(projection)
        if existing is None:
            return True

        self._assert_mutation_allowed()
        try:
            self.service.events().delete(
                calendarId=self.calendar_id,
                eventId=projection["event_id"],
            ).execute()
            return True
        except HttpError as exc:
            status_code = getattr(getattr(exc, "resp", None), "status", None)
            if status_code in (404, 410):
                return True
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
