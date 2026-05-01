import importlib
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))


def _env_without_aws_region():
    return {
        key: value for key, value in os.environ.items() if key not in {"APP_REGION", "AWS_REGION", "AWS_DEFAULT_REGION"}
    }


def _drop_modules(*module_names):
    for module_name in module_names:
        sys.modules.pop(module_name, None)


class ImportBoundaryTests(unittest.TestCase):
    def test_import_config_config_does_not_require_app_region(self):
        _drop_modules("config.config", "utils.dynamodb_utils")

        with patch.dict(os.environ, _env_without_aws_region(), clear=True):
            importlib.import_module("config.config")

        self.assertNotIn("utils.dynamodb_utils", sys.modules)

    def test_import_lambda_utils_does_not_import_dynamodb(self):
        _drop_modules("utils.lambda_utils", "utils.dynamodb_utils")

        with (
            patch.dict(os.environ, _env_without_aws_region(), clear=True),
            patch("boto3.resource") as mock_resource,
        ):
            importlib.import_module("utils.lambda_utils")

        self.assertNotIn("utils.dynamodb_utils", sys.modules)
        mock_resource.assert_not_called()

    def test_batch_summary_does_not_lazy_import_dynamodb(self):
        _drop_modules("utils.lambda_utils", "utils.dynamodb_utils")
        lambda_utils = importlib.import_module("utils.lambda_utils")

        result = lambda_utils.process_and_log_sync_result(
            logger_obj=MagicMock(level=20),
            sync_result={"statusCode": 200, "body": {"status": "ok"}},
            context=MagicMock(function_name="fn", aws_request_id="req"),
            uuid=lambda_utils._BATCH_SUMMARY_UUID,
            lambda_start_time=datetime.now(timezone.utc),
            trigger_name="test",
        )

        self.assertEqual(result["uuid"], lambda_utils._BATCH_SUMMARY_UUID)
        self.assertNotIn("utils.dynamodb_utils", sys.modules)

    def test_real_uuid_lazy_imports_and_calls_save_sync_logs(self):
        _drop_modules("utils.lambda_utils", "utils.dynamodb_utils")
        lambda_utils = importlib.import_module("utils.lambda_utils")
        fake_dynamodb_utils = types.ModuleType("utils.dynamodb_utils")
        fake_dynamodb_utils.save_sync_logs = MagicMock()

        with patch.dict(
            sys.modules,
            {"utils.dynamodb_utils": fake_dynamodb_utils},
        ):
            lambda_utils.process_and_log_sync_result(
                logger_obj=MagicMock(level=20),
                sync_result={"statusCode": 200, "body": {"status": "ok"}},
                context=MagicMock(function_name="fn", aws_request_id="req"),
                uuid="real-uuid",
                lambda_start_time=datetime.now(timezone.utc),
                trigger_name="test",
            )

        fake_dynamodb_utils.save_sync_logs.assert_called_once()
        self.assertEqual(
            fake_dynamodb_utils.save_sync_logs.call_args[0][0],
            "real-uuid",
        )


if __name__ == "__main__":
    unittest.main()
