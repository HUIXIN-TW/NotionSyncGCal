import os
import sys
import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))
TOKEN_CRYPTO_PATH = SRC_ROOT / "utils" / "token_crypto.py"
spec = importlib.util.spec_from_file_location("token_crypto", TOKEN_CRYPTO_PATH)
if not spec or not spec.loader:
    raise ImportError(f"Unable to load token_crypto module from {TOKEN_CRYPTO_PATH}")
token_crypto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(token_crypto)


class _FakeAESGCM:
    def __init__(self, key: bytes):
        self.key = key

    def encrypt(self, iv: bytes, data: bytes, aad):  # noqa: ARG002
        # Fake payload shape: ciphertext + 16-byte auth tag.
        return data + (b"T" * 16)

    def decrypt(self, iv: bytes, payload: bytes, aad):  # noqa: ARG002
        if not payload.endswith(b"T" * 16):
            raise ValueError("bad tag")
        return payload[:-16]


class TokenCryptoTests(unittest.TestCase):
    def setUp(self):
        self.key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    def test_encrypt_and_decrypt(self):
        with (
            patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": self.key}, clear=True),
            patch.object(token_crypto, "_get_aesgcm", return_value=_FakeAESGCM),
            patch.object(token_crypto.os, "urandom", return_value=b"\x00" * 12),
        ):
            encrypted = token_crypto.encrypt_token("my-secret-token")
            self.assertTrue(encrypted.startswith("enc:v1:"))
            decrypted = token_crypto.decrypt_token(encrypted)
            self.assertEqual(decrypted, "my-secret-token")

    def test_encrypt_requires_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.encrypt_token("plain-token")

    def test_decrypt_requires_encrypted_token(self):
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": self.key}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.decrypt_token("plain-token")

    def test_decrypt_token_if_encrypted_returns_plaintext_unchanged(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                token_crypto.decrypt_token_if_encrypted("plain-token"),
                "plain-token",
            )

    def test_decrypt_token_if_encrypted_returns_falsy_values_unchanged(self):
        self.assertIsNone(token_crypto.decrypt_token_if_encrypted(None))
        self.assertEqual(token_crypto.decrypt_token_if_encrypted(""), "")
        self.assertEqual(token_crypto.decrypt_token_if_encrypted(0), 0)

    def test_decrypt_token_if_encrypted_decrypts_encrypted_payload(self):
        with (
            patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": self.key}, clear=True),
            patch.object(token_crypto, "_get_aesgcm", return_value=_FakeAESGCM),
            patch.object(token_crypto.os, "urandom", return_value=b"\x00" * 12),
        ):
            encrypted = token_crypto.encrypt_token("my-secret-token")
            self.assertEqual(
                token_crypto.decrypt_token_if_encrypted(encrypted),
                "my-secret-token",
            )

    def test_decrypt_token_if_encrypted_raises_for_malformed_encrypted_payload(self):
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": self.key}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.decrypt_token_if_encrypted("enc:v1:broken")

    def test_encrypted_payload_requires_key(self):
        encrypted = "enc:v1:000000000000000000000000:54545454545454545454545454545454:616263"
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.decrypt_token(encrypted)

    def test_malformed_payload_raises(self):
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": self.key}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.decrypt_token("enc:v1:broken")

    def test_invalid_key_format_raises(self):
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": "not-hex"}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.encrypt_token("x")

    def test_non_v1_payload_raises(self):
        payload = "enc:v2:000000000000000000000000:54545454545454545454545454545454:616263"
        with (
            patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": self.key}, clear=True),
            patch.object(token_crypto, "_get_aesgcm", return_value=_FakeAESGCM),
        ):
            with self.assertRaises(token_crypto.TokenCryptoError):
                token_crypto.decrypt_token(payload)

    def test_cloud_mode_requires_ssm_path(self):
        with patch.dict(os.environ, {"APP_MODE": "cloud"}, clear=True):
            with self.assertRaises(token_crypto.TokenCryptoError) as ctx:
                token_crypto.encrypt_token("plain-token")
        self.assertIn("TOKEN_ENCRYPTION_KEY_SSM_PATH", str(ctx.exception))

    def test_cloud_mode_uses_ssm_parameter_for_key(self):
        with (
            patch.dict(
                os.environ,
                {"APP_MODE": "cloud", "TOKEN_ENCRYPTION_KEY_SSM_PATH": "/dev/notica/token_encryption_key"},
                clear=True,
            ),
            patch.object(token_crypto, "get_ssm_parameter", return_value=self.key) as mock_ssm,
            patch.object(token_crypto, "_get_aesgcm", return_value=_FakeAESGCM),
            patch.object(token_crypto.os, "urandom", return_value=b"\x00" * 12),
        ):
            encrypted = token_crypto.encrypt_token("my-secret-token")
        mock_ssm.assert_called_once_with("/dev/notica/token_encryption_key")
        self.assertTrue(encrypted.startswith("enc:v1:"))

    def test_cloud_mode_does_not_read_plaintext_key_env(self):
        with (
            patch.dict(
                os.environ,
                {
                    "APP_MODE": "cloud",
                    "TOKEN_ENCRYPTION_KEY": self.key,
                    "TOKEN_ENCRYPTION_KEY_SSM_PATH": "/dev/notica/token_encryption_key",
                },
                clear=True,
            ),
            patch.object(token_crypto, "get_ssm_parameter", return_value="not-a-hex-key"),
        ):
            with self.assertRaises(token_crypto.TokenCryptoError) as ctx:
                token_crypto.encrypt_token("my-secret-token")
        self.assertIn("resolved from SSM", str(ctx.exception))

    def test_local_mode_still_reads_plaintext_key_env(self):
        with (
            patch.dict(os.environ, {"APP_MODE": "local", "TOKEN_ENCRYPTION_KEY": self.key}, clear=True),
            patch.object(token_crypto, "get_ssm_parameter") as mock_ssm,
            patch.object(token_crypto, "_get_aesgcm", return_value=_FakeAESGCM),
            patch.object(token_crypto.os, "urandom", return_value=b"\x00" * 12),
        ):
            encrypted = token_crypto.encrypt_token("my-secret-token")
        mock_ssm.assert_not_called()
        self.assertTrue(encrypted.startswith("enc:v1:"))


if __name__ == "__main__":
    unittest.main()
