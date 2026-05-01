import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

import utils.lambda_utils as lambda_utils  # noqa: E402


def _make_context(function_name="test-fn", aws_request_id="test-req-id"):
    ctx = MagicMock()
    ctx.function_name = function_name
    ctx.aws_request_id = aws_request_id
    return ctx


def _make_logger(level=20):
    lg = MagicMock()
    lg.level = level
    return lg


def _ok_sync_result():
    return {
        "statusCode": 200,
        "body": {"status": "sync_success", "message": {"summary": {}, "errors": []}},
    }


def _make_sqs_event(uuids):
    return {
        "Records": [
            {
                "messageId": f"msg-{i}",
                "body": json.dumps({"uuid": u}),
                "eventSource": "aws:sqs",
            }
            for i, u in enumerate(uuids)
        ]
    }


class TestProcessAndLogSyncResult(unittest.TestCase):
    def setUp(self):
        self.ctx = _make_context()
        self.logger = _make_logger()
        self.start = datetime.now(timezone.utc)

    def _call(self, uuid):
        return lambda_utils.process_and_log_sync_result(
            logger_obj=self.logger,
            sync_result=_ok_sync_result(),
            context=self.ctx,
            uuid=uuid,
            lambda_start_time=self.start,
            trigger_name="test",
        )

    def test_persists_for_real_uuid(self):
        real_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.object(lambda_utils, "_save_sync_logs") as mock_save:
            self._call(real_uuid)
        mock_save.assert_called_once()
        saved_uuid = mock_save.call_args[0][0]
        self.assertEqual(saved_uuid, real_uuid)

    def test_does_not_persist_for_batch_sentinel(self):
        with patch.object(lambda_utils, "_save_sync_logs") as mock_save:
            result = self._call(lambda_utils._BATCH_SUMMARY_UUID)
        mock_save.assert_not_called()
        self.assertEqual(result["uuid"], lambda_utils._BATCH_SUMMARY_UUID)

    def test_does_not_persist_for_none_uuid(self):
        with patch.object(lambda_utils, "_save_sync_logs") as mock_save:
            self._call(None)
        mock_save.assert_not_called()


class TestProcessSqsRecords(unittest.TestCase):
    def setUp(self):
        self.ctx = _make_context()
        self.logger = _make_logger()
        self.start = datetime.now(timezone.utc)

    def _run_sync(self, uuid):
        return _ok_sync_result()

    def _process(self, uuids):
        return lambda_utils.process_sqs_records(
            logger_obj=self.logger,
            event=_make_sqs_event(uuids),
            context=self.ctx,
            run_sync=self._run_sync,
            lambda_start_time=self.start,
        )

    def test_each_record_saved_under_its_real_uuid(self):
        uuids = ["uuid-001", "uuid-002"]
        with patch.object(lambda_utils, "_save_sync_logs") as mock_save:
            self._process(uuids)
        self.assertEqual(mock_save.call_count, len(uuids))
        saved_uuids = [c[0][0] for c in mock_save.call_args_list]
        self.assertEqual(saved_uuids, uuids)

    def test_save_sync_logs_never_called_with_batch_sentinel(self):
        with patch.object(lambda_utils, "_save_sync_logs") as mock_save:
            self._process(["uuid-aaa", "uuid-bbb"])
        saved_uuids = [c[0][0] for c in mock_save.call_args_list]
        self.assertNotIn(lambda_utils._BATCH_SUMMARY_UUID, saved_uuids)

    def test_batch_summary_uuid_is_sentinel(self):
        with patch.object(lambda_utils, "_save_sync_logs"):
            result = self._process(["uuid-xyz"])
        self.assertEqual(result["uuid"], lambda_utils._BATCH_SUMMARY_UUID)

    def test_batch_summary_contains_record_summaries(self):
        uuids = ["uuid-p", "uuid-q"]
        with patch.object(lambda_utils, "_save_sync_logs"):
            result = self._process(uuids)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(result["failure_count"], 0)
        self.assertCountEqual(result["success_uuids"], uuids)
        self.assertEqual(result["failure_uuids"], [])


if __name__ == "__main__":
    unittest.main()
