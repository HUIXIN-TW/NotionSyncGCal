import logging
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from utils.logging_utils import (  # noqa: E402
    build_debug_exception_detail,
    get_logger,
    is_non_production,
    is_production_environment,
    should_expose_debug_sync_error,
)


class LoggingUtilsTests(unittest.TestCase):
    def _logger_name(self, suffix: str) -> str:
        return f"test.logging_utils.{suffix}.{id(self)}"

    def test_production_environment_is_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(is_production_environment())
            self.assertFalse(is_non_production())

    def test_non_production_environment_detection(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            self.assertTrue(is_non_production())
            self.assertFalse(is_production_environment())

    def test_debug_sync_error_flag_ignored_in_production(self):
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "EXPOSE_DEBUG_SYNC_ERRORS": "true"},
            clear=True,
        ):
            self.assertFalse(should_expose_debug_sync_error())

    def test_debug_sync_error_flag_enabled_in_non_production(self):
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "EXPOSE_DEBUG_SYNC_ERRORS": "yes"},
            clear=True,
        ):
            self.assertTrue(should_expose_debug_sync_error())

    def test_build_debug_exception_detail_requires_explicit_flag(self):
        err = RuntimeError("provider detail")
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "EXPOSE_DEBUG_SYNC_ERRORS": "false"},
            clear=True,
        ):
            self.assertIsNone(build_debug_exception_detail(err))

        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "EXPOSE_DEBUG_SYNC_ERRORS": "true"},
            clear=True,
        ):
            self.assertEqual(
                build_debug_exception_detail(err),
                "RuntimeError: provider detail",
            )

    def test_get_logger_uses_info_in_production(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            logger = get_logger(self._logger_name("prod"))
            self.assertEqual(logger.level, logging.INFO)

    def test_get_logger_uses_debug_in_non_production(self):
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True):
            logger = get_logger(self._logger_name("dev"))
            self.assertEqual(logger.level, logging.DEBUG)


if __name__ == "__main__":
    unittest.main()
