import os
import re
from utils.ssm_secrets import SSMSecretError, get_ssm_parameter

TOKEN_ENCRYPTION_PREFIX = "enc:v1:"
TOKEN_ENCRYPTION_KEY_ENV = "TOKEN_ENCRYPTION_KEY"
TOKEN_ENCRYPTION_KEY_SSM_PATH_ENV = "TOKEN_ENCRYPTION_KEY_SSM_PATH"
_KEY_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_TOKEN_IV_BYTES = 12
_TOKEN_TAG_BYTES = 16


class TokenCryptoError(ValueError):
    """Raised when a token cannot be encrypted or decrypted."""


def _get_aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise TokenCryptoError("Token encryption requires 'cryptography'. Install dependencies with: uv sync") from exc
    return AESGCM


def _get_key_bytes() -> bytes:
    app_mode = (os.getenv("APP_MODE") or "").strip().lower()

    if app_mode == "cloud":
        ssm_path = os.getenv(TOKEN_ENCRYPTION_KEY_SSM_PATH_ENV, "").strip()
        if not ssm_path:
            raise TokenCryptoError("TOKEN_ENCRYPTION_KEY_SSM_PATH env var is required but not set in APP_MODE=cloud.")
        try:
            raw = get_ssm_parameter(ssm_path).strip()
        except SSMSecretError as exc:
            raise TokenCryptoError(f"Failed to resolve TOKEN_ENCRYPTION_KEY from SSM: {exc}") from exc
        source_name = "TOKEN_ENCRYPTION_KEY resolved from SSM"
    else:
        raw = os.getenv(TOKEN_ENCRYPTION_KEY_ENV, "").strip()
        if not raw:
            raise TokenCryptoError("TOKEN_ENCRYPTION_KEY env var is required but not set.")
        source_name = "TOKEN_ENCRYPTION_KEY"

    if not _KEY_HEX_PATTERN.match(raw):
        raise TokenCryptoError(f"{source_name} must be a 64-character hex string.")
    return bytes.fromhex(raw)


def decrypt_token(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    if not value.startswith(TOKEN_ENCRYPTION_PREFIX):
        raise TokenCryptoError(
            f"Token is not encrypted (expected '{TOKEN_ENCRYPTION_PREFIX}' prefix). "
            "All tokens in the database must be encrypted."
        )

    key = _get_key_bytes()
    parts = value.split(":")
    if len(parts) != 5:
        raise TokenCryptoError("Malformed encrypted token payload.")

    _, version, iv_hex, tag_hex, ciphertext_hex = parts
    if version != "v1":
        raise TokenCryptoError(f"Unsupported encrypted token version: {version}")

    try:
        iv = bytes.fromhex(iv_hex)
        auth_tag = bytes.fromhex(tag_hex)
        ciphertext = bytes.fromhex(ciphertext_hex)
    except ValueError as exc:
        raise TokenCryptoError("Encrypted token payload contains invalid hex data.") from exc

    if len(iv) != _TOKEN_IV_BYTES:
        raise TokenCryptoError("Encrypted token payload has invalid IV length.")
    if len(auth_tag) != _TOKEN_TAG_BYTES:
        raise TokenCryptoError("Encrypted token payload has invalid auth tag length.")

    aesgcm_cls = _get_aesgcm()
    try:
        plaintext = aesgcm_cls(key).decrypt(iv, ciphertext + auth_tag, None)
        return plaintext.decode("utf-8")
    except Exception as exc:  # pragma: no cover - exact crypto exception type is library-specific
        raise TokenCryptoError("Failed to decrypt encrypted token payload.") from exc


def decrypt_token_if_encrypted(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(TOKEN_ENCRYPTION_PREFIX):
        return decrypt_token(value)
    return value


def encrypt_token_if_plaintext(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    if value.startswith(TOKEN_ENCRYPTION_PREFIX):
        # Validate prefixed payloads so malformed enc:v1 values are never
        # treated as plaintext and re-encrypted.
        decrypt_token(value)
        return value
    return encrypt_token(value)


def encrypt_token(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value

    key = _get_key_bytes()
    aesgcm_cls = _get_aesgcm()
    iv = os.urandom(_TOKEN_IV_BYTES)
    payload = aesgcm_cls(key).encrypt(iv, value.encode("utf-8"), None)
    ciphertext = payload[:-_TOKEN_TAG_BYTES]
    auth_tag = payload[-_TOKEN_TAG_BYTES:]
    return f"{TOKEN_ENCRYPTION_PREFIX}{iv.hex()}:{auth_tag.hex()}:{ciphertext.hex()}"
