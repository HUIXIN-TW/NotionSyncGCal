import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from utils import ssm_secrets  # noqa: E402


class SSMSecretsTests(unittest.TestCase):
    def setUp(self):
        ssm_secrets._SSM_CLIENT = None
        ssm_secrets._PARAMETER_CACHE.clear()

    def test_get_ssm_parameter_fetches_with_decryption(self):
        mock_client = MagicMock()
        mock_client.get_parameter.return_value = {"Parameter": {"Value": "secret-value"}}

        with patch.object(ssm_secrets, "_get_ssm_client", return_value=mock_client):
            value = ssm_secrets.get_ssm_parameter("/dev/notica/secret")

        self.assertEqual(value, "secret-value")
        mock_client.get_parameter.assert_called_once_with(Name="/dev/notica/secret", WithDecryption=True)

    def test_get_ssm_parameter_caches_values(self):
        mock_client = MagicMock()
        mock_client.get_parameter.return_value = {"Parameter": {"Value": "secret-value"}}

        with patch.object(ssm_secrets, "_get_ssm_client", return_value=mock_client):
            first = ssm_secrets.get_ssm_parameter("/dev/notica/secret")
            second = ssm_secrets.get_ssm_parameter("/dev/notica/secret")

        self.assertEqual(first, "secret-value")
        self.assertEqual(second, "secret-value")
        mock_client.get_parameter.assert_called_once()

    def test_missing_region_raises_clear_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ssm_secrets.SSMSecretError) as ctx:
                ssm_secrets._resolve_region()
        self.assertIn("APP_REGION", str(ctx.exception))
        self.assertIn("AWS_REGION", str(ctx.exception))

    def test_ssm_client_is_created_lazily(self):
        fake_boto3 = MagicMock()
        fake_client = MagicMock()
        fake_boto3.client.return_value = fake_client

        with patch.dict(os.environ, {"APP_REGION": "ap-southeast-2"}, clear=True):
            with patch.dict(sys.modules, {"boto3": fake_boto3}):
                self.assertIsNone(ssm_secrets._SSM_CLIENT)
                client = ssm_secrets._get_ssm_client()

        self.assertIs(client, fake_client)
        fake_boto3.client.assert_called_once_with("ssm", region_name="ap-southeast-2")

    def test_parameter_value_is_not_logged(self):
        mock_client = MagicMock()
        mock_client.get_parameter.return_value = {"Parameter": {"Value": "super-secret-value"}}

        with patch.object(ssm_secrets, "_get_ssm_client", return_value=mock_client):
            with patch("builtins.print") as mock_print:
                ssm_secrets.get_ssm_parameter("/dev/notica/secret")

        mock_print.assert_not_called()


if __name__ == "__main__":
    unittest.main()
