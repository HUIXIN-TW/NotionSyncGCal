from notion_client import Client
from notion_client.errors import APIResponseError


NOTION_API_VERSION_2022 = "2022-06-28"


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class NotionService:
    def __init__(self, token, user_setting, logger):
        self.logger = logger
        self.token = token
        self.setting = user_setting
        self.page_property = self.setting["page_property"]
        self.notion_api_version = self.setting.get("notion_api_version", NOTION_API_VERSION_2022)

        try:
            self.client = Client(auth=self.token, notion_version=self.notion_api_version)
            self.logger.debug(f"Notion client initialized successfully with API version {self.notion_api_version}.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Notion client: {e}")
            raise SettingError(f"Failed to initialize Notion client: {e}")

    def test_connection(self):
        try:
            self.client.users.me()
            self.logger.info("Notion connection passed.")
            return True
        except APIResponseError as e:
            self.logger.error(f"Notion API error: {e}. Please click 'view settings' and re-authorize the integration.")
            return False
        except Exception as e:
            self.logger.error(f"Notion Connection failed: {e}. Please check your network connection.")
            return False

    def _query_database_with_pagination(self, **query_kwargs):
        results = []
        next_cursor = None
        page_number = 0
        database_id = query_kwargs["database_id"]
        request_body = {key: value for key, value in query_kwargs.items() if key != "database_id"}

        while True:
            page_number += 1
            paginated_query_kwargs = {**request_body, "page_size": 100}
            if next_cursor:
                paginated_query_kwargs["start_cursor"] = next_cursor

            response = self.client.request(
                path=f"databases/{database_id}/query",
                method="POST",
                body=paginated_query_kwargs,
            )
            page_results = response.get("results", [])
            results.extend(page_results)
            self.logger.debug(
                "Notion query page %s fetched %s rows; total rows so far: %s",
                page_number,
                len(page_results),
                len(results),
            )

            if not response.get("has_more"):
                break

            next_cursor = response.get("next_cursor")

        return results

    def get_notion_task(self):

        # TODO: Notion has no filter for start date and end date so add extra column: GCAL_END_DATE_NOTION_NAME
        before_date_with_time_zone = self.setting["google_timemax"]
        after_date_with_time_zone = self.setting["google_timemin"]
        date_range = f"from {self.setting['after_date']} (inclusive) to {self.setting['before_date']} (exclusive)"
        notion_summary = {
            "action": "get_notion_task",
            "database_id": self.setting["database_id"],
            "notion_api_version": self.notion_api_version,
            "range": date_range,
        }

        self.logger.debug(notion_summary)

        try:
            return (
                notion_summary,
                self._query_database_with_pagination(
                    database_id=self.setting["database_id"],
                    filter={
                        "and": [
                            {
                                "property": self.page_property["Date_Notion_Name"],
                                "date": {"before": before_date_with_time_zone},
                            },
                            {
                                "property": self.page_property["GCal_End_Date_Notion_Name"],
                                "formula": {"date": {"on_or_after": after_date_with_time_zone}},
                            },
                        ]
                    },
                ),
            )
        except Exception as e:
            error_message = f"Error reading Notion table: {e}"
            self.logger.error(error_message)
            raise SettingError(error_message)

    def get_page_property(self, key: str) -> str:
        return self.setting["page_property"].get(key)
