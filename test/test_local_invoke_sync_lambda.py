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
        self.assertNotIn("TOKEN_ENCRYPTION_KEY", required)
        self.assertNotIn("GOOGLE_CALENDAR_CLIENT_SECRET", required)


if __name__ == "__main__":
    unittest.main()
