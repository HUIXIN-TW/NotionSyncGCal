import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

google_module = types.ModuleType("google")
google_auth_module = types.ModuleType("google.auth")
google_auth_exceptions_module = types.ModuleType("google.auth.exceptions")


class _RefreshError(Exception):
    pass


google_auth_exceptions_module.RefreshError = _RefreshError
google_auth_module.exceptions = google_auth_exceptions_module
google_module.auth = google_auth_module
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.auth", google_auth_module)
sys.modules.setdefault("google.auth.exceptions", google_auth_exceptions_module)

import lambda_function  # noqa: E402
from google.auth.exceptions import RefreshError  # noqa: E402


def _make_context(function_name="test-lambda", aws_request_id="req-123"):
    return type(
        "FakeContext",
        (),
        {
            "function_name": function_name,
            "aws_request_id": aws_request_id,
        },
    )()


def _make_sqs_event(*uuids):
    return {
        "Records": [
            {
                "messageId": f"msg-{index}",
                "body": json.dumps({"uuid": uuid}),
                "eventSource": "aws:sqs",
            }
            for index, uuid in enumerate(uuids)
        ]
    }


class LambdaHandlerTests(unittest.TestCase):
    def _stub_src_main(self):
        module = types.ModuleType("src.main")
        module.main = lambda uuid=None: {"statusCode": 200, "body": {"status": "sync_success", "message": uuid}}
        return patch.dict(sys.modules, {"src.main": module})

    def test_api_event_returns_explicit_501_payload(self):
        event = {"requestContext": {"http": {"method": "POST"}}}
        context = _make_context()

        with patch.object(lambda_function, "detect_event_source", return_value="api"):
            result = lambda_function.lambda_handler(event, context)

        self.assertEqual(result["statusCode"], 501)
        self.assertEqual(result["body"]["status"], "sync_error")
        self.assertEqual(result["body"]["message"]["error_code"], "unsupported_event_source")
        self.assertEqual(result["body"]["message"]["aws_request_id"], "req-123")

    def test_unhandled_sqs_failure_returns_all_batch_item_failures(self):
        event = _make_sqs_event("uuid-1", "uuid-2")
        context = _make_context()

        with self._stub_src_main():
            with patch.object(lambda_function, "detect_event_source", return_value="sqs"):
                with patch.object(
                    lambda_function,
                    "process_sqs_records",
                    side_effect=RuntimeError("boom"),
                ):
                    result = lambda_function.lambda_handler(event, context)

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(
            result["batchItemFailures"],
            [{"itemIdentifier": "msg-0"}, {"itemIdentifier": "msg-1"}],
        )
        self.assertEqual(result["body"]["message"]["error_code"], "lambda_unhandled_error")

    def test_refresh_error_returns_sqs_batch_item_failures(self):
        event = _make_sqs_event("uuid-1")
        context = _make_context()

        with self._stub_src_main():
            with patch.object(lambda_function, "detect_event_source", return_value="sqs"):
                with patch.object(
                    lambda_function,
                    "process_sqs_records",
                    side_effect=RefreshError("invalid_grant"),
                ):
                    result = lambda_function.lambda_handler(event, context)

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["batchItemFailures"], [{"itemIdentifier": "msg-0"}])
        self.assertEqual(result["body"]["message"]["error_code"], "google_refresh_error")

    def test_detect_event_source_failure_returns_safe_500_payload(self):
        event = {"detail-type": "scheduled", "source": "aws.events"}
        context = _make_context()

        with patch.object(
            lambda_function,
            "detect_event_source",
            side_effect=RuntimeError("broken detector"),
        ):
            result = lambda_function.lambda_handler(event, context)

        self.assertEqual(result["statusCode"], 500)
        self.assertEqual(result["body"]["status"], "sync_error")
        self.assertEqual(result["body"]["message"]["error_code"], "lambda_unhandled_error")


if __name__ == "__main__":
    unittest.main()
