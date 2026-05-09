import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from utils.dynamodb_utils import get_google_token_by_uuid, update_google_token_by_uuid  # noqa: E402
from utils.token_crypto import TokenCryptoError  # noqa: E402


class DynamoDbGoogleTokenTests(unittest.TestCase):
    def test_get_google_token_decrypts_encrypted_fields(self):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {
                "uuid": "u-1",
                "accessToken": "enc:v1:encrypted-access",
                "refreshToken": "enc:v1:encrypted-refresh",
            }
        }
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.decrypt_token_if_encrypted", side_effect=["plain-access", "plain-refresh"]
            ):
                item = get_google_token_by_uuid("u-1")
        self.assertEqual(item["accessToken"], "plain-access")
        self.assertEqual(item["refreshToken"], "plain-refresh")

    def test_get_google_token_keeps_legacy_plaintext_fields(self):
        table = MagicMock()
        table.get_item.return_value = {
            "Item": {
                "uuid": "u-1",
                "accessToken": "plain-access",
                "refreshToken": "plain-refresh",
            }
        }
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            item = get_google_token_by_uuid("u-1")
        self.assertEqual(item["accessToken"], "plain-access")
        self.assertEqual(item["refreshToken"], "plain-refresh")

    def test_update_google_token_encrypts_plaintext_fields(self):
        table = MagicMock()
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=["enc:v1:access", "enc:v1:refresh"],
            ) as mock_encrypt:
                update_google_token_by_uuid("u-1", "plain-access", "plain-refresh", "111", "222")

        self.assertEqual(mock_encrypt.call_args_list[0].args[0], "plain-access")
        self.assertEqual(mock_encrypt.call_args_list[1].args[0], "plain-refresh")

        kwargs = table.update_item.call_args.kwargs
        self.assertEqual(kwargs["Key"], {"uuid": "u-1"})
        self.assertEqual(kwargs["ExpressionAttributeValues"][":at"], "enc:v1:access")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":rt"], "enc:v1:refresh")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":expiry"], "111")
        self.assertEqual(kwargs["ExpressionAttributeValues"][":updated"], "222")

    def test_update_google_token_does_not_double_encrypt_prefixed_values(self):
        table = MagicMock()
        access = "enc:v1:access"
        refresh = "enc:v1:refresh"
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch("utils.dynamodb_utils.encrypt_token_if_plaintext", side_effect=[access, refresh]):
                update_google_token_by_uuid("u-1", access, refresh, "111", "222")

        values = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(values[":at"], access)
        self.assertEqual(values[":rt"], refresh)

    def test_update_google_token_raises_for_malformed_prefixed_value(self):
        table = MagicMock()
        with patch("utils.dynamodb_utils._get_google_tables", return_value=table):
            with patch(
                "utils.dynamodb_utils.encrypt_token_if_plaintext",
                side_effect=TokenCryptoError("Malformed encrypted token payload."),
            ):
                with self.assertRaises(TokenCryptoError):
                    update_google_token_by_uuid("u-1", "enc:v1:broken", "plain-refresh", "111", "222")
        table.update_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
