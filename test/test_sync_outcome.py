import sys
import unittest
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from sync.contracts import (  # noqa: E402
    SyncOutcomeKind,
    build_capacity_limited_result,
    build_sync_result,
    classify_sync_result,
)


class SyncOutcomeContractTests(unittest.TestCase):
    def test_clean_success(self):
        execution = classify_sync_result(
            build_sync_result(200, "sync_success", {"summary": {}, "errors": []})
        )

        self.assertEqual(execution.outcome.kind, SyncOutcomeKind.SUCCESS)
        self.assertFalse(execution.outcome.requires_retry)
        self.assertTrue(execution.outcome.counts_as_batch_success)

    def test_non_retriable_partial_preserves_batch_success_semantics(self):
        execution = classify_sync_result(
            build_sync_result(
                200,
                "sync_success",
                {"errors": [{"error_code": "skipped_item", "retriable": False}]},
            )
        )

        self.assertEqual(
            execution.outcome.kind,
            SyncOutcomeKind.PARTIAL_NON_RETRIABLE,
        )
        self.assertFalse(execution.outcome.requires_retry)
        self.assertTrue(execution.outcome.counts_as_batch_success)

    def test_retriable_error_overrides_nominal_success_fields(self):
        execution = classify_sync_result(
            build_sync_result(
                200,
                "sync_success",
                {"errors": [{"error_code": "provider_write_failed", "retriable": True}]},
            )
        )

        self.assertEqual(
            execution.outcome.kind,
            SyncOutcomeKind.RETRIABLE_FAILURE,
        )
        self.assertTrue(execution.outcome.requires_retry)
        self.assertFalse(execution.outcome.counts_as_batch_success)

    def test_5xx_is_retriable_failure(self):
        execution = classify_sync_result(
            build_sync_result(500, "sync_error", {"error_code": "runtime_error"})
        )

        self.assertEqual(
            execution.outcome.kind,
            SyncOutcomeKind.RETRIABLE_FAILURE,
        )
        self.assertTrue(execution.outcome.requires_retry)

    def test_non_retriable_4xx_is_fatal_failure(self):
        execution = classify_sync_result(
            build_sync_result(
                409,
                "sync_error",
                {"error_code": "sync_configuration_invalid", "retriable": False},
            )
        )

        self.assertEqual(execution.outcome.kind, SyncOutcomeKind.FATAL_FAILURE)
        self.assertFalse(execution.outcome.requires_retry)
        self.assertFalse(execution.outcome.counts_as_batch_success)

    def test_capacity_limit_is_partial_non_retriable(self):
        execution = classify_sync_result(
            build_capacity_limited_result(
                sync_task_limit=250,
                trigger_sync_time="2026-09-29T00:00:00Z",
                event_count=0,
                task_count=251,
            )
        )

        self.assertEqual(
            execution.outcome.kind,
            SyncOutcomeKind.PARTIAL_NON_RETRIABLE,
        )
        self.assertFalse(execution.outcome.requires_retry)
        self.assertTrue(execution.outcome.counts_as_batch_success)

    def test_unknown_success_status_fails_closed(self):
        execution = classify_sync_result(
            {"statusCode": 200, "body": {"status": "unknown", "message": "unexpected"}}
        )

        self.assertEqual(execution.outcome.kind, SyncOutcomeKind.FATAL_FAILURE)
        self.assertFalse(execution.outcome.counts_as_batch_success)


if __name__ == "__main__":
    unittest.main()
