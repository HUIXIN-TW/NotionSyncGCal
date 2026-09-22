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
                "page_property": {"GCal_EventId_Notion_Name": "GCal Event Id"},
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


if __name__ == "__main__":
    unittest.main()
