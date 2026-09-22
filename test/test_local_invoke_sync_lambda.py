import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import scripts.local_invoke_sync_lambda as local_invoke  # noqa: E402


class LocalInvokeCloudEnvValidationTests(unittest.TestCase):
    def test_cloud_requires_ssm_path_env_vars_not_plaintext_secrets(self):
        logger = MagicMock()
        captured = {}

        def capture_require_env(names):
            captured["names"] = names

        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with patch.object(local_invoke, "_require_env", side_effect=capture_require_env):
                with patch.object(local_invoke, "_call_with_isolated_argv", return_value={"statusCode": 200}):
                    with patch("lambda_function.lambda_handler", return_value={"statusCode": 200}):
                        local_invoke._invoke_cloud("test-uuid", logger)

        required = captured["names"]
        self.assertIn("TOKEN_ENCRYPTION_KEY_SSM_PATH", required)
        self.assertIn("GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH", required)
        self.assertIn("DYNAMODB_MAPPING_DOMAIN_TABLE", required)
        self.assertNotIn("TOKEN_ENCRYPTION_KEY", required)
        self.assertNotIn("GOOGLE_CALENDAR_CLIENT_SECRET", required)


class ReadOnlyCloudConfigCheckTests(unittest.TestCase):
    def test_config_check_requires_only_mapping_table_and_region(self):
        logger = MagicMock()
        captured = {}

        def capture_require_env(names):
            captured["names"] = names

        source_settings = [
            {
                "source_id": "source-1",
                "database_id": "db-1",
                "timezone": "Asia/Taipei",
                "timecode": "+08:00",
                "goback_days": 7,
                "goforward_days": 100,
                "gcal_default_name": "Learning",
                "gcal_name_dict": {"Learning": "calendar-id"},
                "page_property": {"GCal_EventId_Notion_Name": "event-id"},
            }
        ]

        with patch.dict(
            os.environ,
            {
                "APP_MODE": "cloud",
                "DYNAMODB_MAPPING_DOMAIN_TABLE": "mapping-table",
                "APP_REGION": "ap-southeast-2",
            },
            clear=True,
        ):
            with patch.object(local_invoke, "_require_env", side_effect=capture_require_env):
                with patch("config.mapping_domain_config.MappingDomainConfig") as mapping_config:
                    mapping_config.return_value.get.return_value = source_settings
                    result = local_invoke._check_cloud_config("user-1", logger)

        self.assertEqual(captured["names"], ["DYNAMODB_MAPPING_DOMAIN_TABLE", "APP_REGION"])
        self.assertEqual(result["statusCode"], 200)
        message = result["body"]["message"]
        self.assertTrue(message["read_only"])
        self.assertEqual(message["source_count"], 1)
        self.assertEqual(message["sources"][0]["default_calendar_name"], "Learning")
        self.assertEqual(
            message["sources"][0]["property_ids"]["GCal_EventId_Notion_Name"],
            "event-id",
        )
        self.assertNotIn("calendar-id", str(message))
        self.assertNotIn("token", str(message).lower())

    def test_safe_summary_exposes_names_not_calendar_ids(self):
        source_settings = [
            {
                "source_id": "source-1",
                "database_id": "db-1",
                "timezone": "Asia/Taipei",
                "timecode": "+08:00",
                "goback_days": 7,
                "goforward_days": 100,
                "gcal_default_name": "Learning",
                "gcal_name_dict": {
                    "Learning": "secret-calendar-id-1",
                    "Job": "secret-calendar-id-2",
                },
                "page_property": {
                    "GCal_EventId_Notion_Name": "GCal Event Id",
                    "GCal_Sync_Time_Notion_Name": "GCal Sync Time",
                },
            }
        ]
        result = local_invoke._build_safe_config_summary("user-1", source_settings)
        message = result["body"]["message"]
        self.assertEqual(message["sources"][0]["calendar_names"], ["Learning", "Job"])
        self.assertNotIn("secret-calendar-id", str(message))


class ReadOnlyProviderMatchTests(unittest.TestCase):
    def test_provider_match_counts_existing_event_ids_without_sync_mutations(self):
        logger = MagicMock()
        source_setting = {
            "source_id": "source-1",
            "page_property": {"GCal_EventId_Notion_Name": "event-id-property"},
        }
        notion_tasks = [
            {
                "properties": {
                    "GCal Event Id": {
                        "id": "event-id-property",
                        "rich_text": [{"plain_text": "event-1"}],
                    }
                }
            },
            {
                "properties": {
                    "GCal Event Id": {
                        "id": "event-id-property",
                        "rich_text": [{"plain_text": "event-2"}],
                    }
                }
            },
        ]
        google_events = [{"id": "event-1"}, {"id": "event-2"}]

        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with patch.object(local_invoke, "_require_env"):
                with patch("config.mapping_domain_config.MappingDomainConfig") as mapping_config:
                    mapping_config.return_value.get.return_value = [source_setting]
                    with patch("notion.notion_token.NotionToken") as notion_token:
                        notion_token.return_value.get.return_value = "notion-token"
                        with patch("gcal.gcal_token.GoogleToken") as google_token:
                            with patch("notion.notion_service.NotionService") as notion_service:
                                notion_service.return_value.get_notion_task.return_value = ({}, notion_tasks)
                                with patch("gcal.gcal_service.GoogleService") as google_service:
                                    google_service.return_value.get_gcal_event.return_value = google_events
                                    result = local_invoke._check_cloud_provider_match("user-1", logger)

        self.assertEqual(result["statusCode"], 200)
        message = result["body"]["message"]
        self.assertTrue(message["read_only_provider_data"])
        self.assertEqual(message["notion_tasks_with_event_id"], 2)
        self.assertEqual(message["matched_event_ids"], 2)
        self.assertEqual(message["missing_event_ids"], 0)
        self.assertEqual(message["duplicate_notion_event_ids"], 0)
        notion_service.return_value.update_notion_task.assert_not_called()
        notion_service.return_value.create_notion_task.assert_not_called()
        notion_service.return_value.delete_notion_task.assert_not_called()
        google_service.return_value.update_gcal_event.assert_not_called()
        google_service.return_value.create_gcal_event.assert_not_called()
        google_service.return_value.delete_gcal_event.assert_not_called()
        google_token.assert_called_once()

    def test_provider_match_fails_when_existing_event_id_is_missing(self):
        logger = MagicMock()
        source_setting = {
            "source_id": "source-1",
            "page_property": {"GCal_EventId_Notion_Name": "event-id-property"},
        }
        notion_tasks = [
            {
                "properties": {
                    "GCal Event Id": {
                        "id": "event-id-property",
                        "rich_text": [{"plain_text": "event-missing"}],
                    }
                }
            }
        ]

        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with patch.object(local_invoke, "_require_env"):
                with patch("config.mapping_domain_config.MappingDomainConfig") as mapping_config:
                    mapping_config.return_value.get.return_value = [source_setting]
                    with patch("notion.notion_token.NotionToken") as notion_token:
                        notion_token.return_value.get.return_value = "notion-token"
                        with patch("gcal.gcal_token.GoogleToken"):
                            with patch("notion.notion_service.NotionService") as notion_service:
                                notion_service.return_value.get_notion_task.return_value = ({}, notion_tasks)
                                with patch("gcal.gcal_service.GoogleService") as google_service:
                                    google_service.return_value.get_gcal_event.return_value = []
                                    result = local_invoke._check_cloud_provider_match("user-1", logger)

        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(result["body"]["message"]["missing_event_ids"], 1)


class OnePairProviderCanaryTests(unittest.TestCase):
    def _source_setting(self):
        return {
            "source_id": "source-1",
            "database_id": "05482e3c-4aca-40e0-9527-9ff2f2630e66",
            "gcal_default_name": "Learning",
            "gcal_name_dict": {"Learning": "calendar-1@example.com"},
            "page_property": {
                "GCal_EventId_Notion_Name": "event-id-property",
                "Delete_Notion_Name": "delete-property",
                "GCal_Name_Notion_Name": "calendar-name-property",
            },
        }

    def _page(self, *, deleted=False):
        return {
            "id": "page-1",
            "parent": {"database_id": "05482e3c-4aca-40e0-9527-9ff2f2630e66"},
            "properties": {
                "GCal Event Id": {
                    "id": "event-id-property",
                    "rich_text": [{"plain_text": "event-1"}],
                },
                "Delete": {"id": "delete-property", "checkbox": deleted},
                "Calendar": {
                    "id": "calendar-name-property",
                    "select": {"name": "Learning"},
                },
            },
        }

    def test_one_pair_canary_uses_existing_pair_and_preserves_event_count(self):
        logger = MagicMock()
        page = self._page()
        existing_event = {"id": "event-1", "organizer": {"email": "calendar-1@example.com"}}
        notion_service = MagicMock()
        notion_service.client.pages.retrieve.return_value = page
        google_service = MagicMock()
        google_service.get_gcal_event.side_effect = [[existing_event], [existing_event]]

        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with patch.object(local_invoke, "_require_env"):
                with patch("config.mapping_domain_config.MappingDomainConfig") as mapping_config:
                    mapping_config.return_value.get.return_value = [self._source_setting()]
                    with patch("notion.notion_token.NotionToken") as notion_token:
                        notion_token.return_value.get.return_value = "notion-token"
                        with patch("gcal.gcal_token.GoogleToken"):
                            with patch("notion.notion_service.NotionService", return_value=notion_service):
                                with patch("gcal.gcal_service.GoogleService", return_value=google_service):
                                    with patch(
                                        "sync.sync.force_update_google_event_by_notion_task_and_ignore_time",
                                        return_value={"statusCode": 200, "body": {"status": "sync_success"}},
                                    ) as sync_fn:
                                        result = local_invoke._run_cloud_canary(
                                            "user-1",
                                            "page-1",
                                            "page-1",
                                            logger,
                                        )

        self.assertEqual(result["statusCode"], 200)
        message = result["body"]["message"]
        self.assertTrue(message["same_event_preserved"])
        self.assertEqual(message["google_event_count_before"], 1)
        self.assertEqual(message["google_event_count_after"], 1)
        scoped_notion = sync_fn.call_args.kwargs["notion_service"]
        scoped_google = sync_fn.call_args.kwargs["google_service"]
        self.assertEqual(scoped_notion.get_notion_task()[1], [page])
        self.assertEqual(scoped_google.get_gcal_event(), [existing_event])

    def test_one_pair_canary_refuses_delete_flag_before_sync(self):
        logger = MagicMock()
        page = self._page(deleted=True)
        notion_service = MagicMock()
        notion_service.client.pages.retrieve.return_value = page

        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with patch.object(local_invoke, "_require_env"):
                with patch("config.mapping_domain_config.MappingDomainConfig") as mapping_config:
                    mapping_config.return_value.get.return_value = [self._source_setting()]
                    with patch("notion.notion_token.NotionToken") as notion_token:
                        notion_token.return_value.get.return_value = "notion-token"
                        with patch("gcal.gcal_token.GoogleToken"):
                            with patch("notion.notion_service.NotionService", return_value=notion_service):
                                with patch(
                                    "sync.sync.force_update_google_event_by_notion_task_and_ignore_time"
                                ) as sync_fn:
                                    result = local_invoke._run_cloud_canary(
                                        "user-1",
                                        "page-1",
                                        "page-1",
                                        logger,
                                    )

        self.assertEqual(result["statusCode"], 409)
        self.assertEqual(result["body"]["status"], "canary_refused")
        sync_fn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
