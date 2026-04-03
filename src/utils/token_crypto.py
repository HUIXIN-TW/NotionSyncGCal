import os
import re

TOKEN_ENCRYPTION_PREFIX = "enc:v1:"
TOKEN_ENCRYPTION_KEY_ENV = "TOKEN_ENCRYPTION_KEY"
_KEY_HEX_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_TOKEN_IV_BYTES = 12
_TOKEN_TAG_BYTES = 16


class TokenCryptoError(ValueError):
    """Raised when encrypted token payload cannot be processed."""


def _get_aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise TokenCryptoError(
            "Encrypted token support requires 'cryptography'. Install dependencies from requirements.txt."
        ) from exc
    return AESGCM


def _get_key_bytes() -> bytes | None:
    raw = os.getenv(TOKEN_ENCRYPTION_KEY_ENV, "").strip()
    if not raw:
        return None
    if not _KEY_HEX_PATTERN.match(raw):
        raise TokenCryptoError("TOKEN_ENCRYPTION_KEY must be a 64-character hex string.")
    return bytes.fromhex(raw)


def is_encrypted_token(value: str) -> bool:
    return isinstance(value, str) and value.startswith(TOKEN_ENCRYPTION_PREFIX)


def decrypt_token_if_needed(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    if value.startswith("enc:") and not value.startswith(TOKEN_ENCRYPTION_PREFIX):
        raise TokenCryptoError("Unsupported encrypted token version prefix.")
    if not is_encrypted_token(value):
        # Backward compatibility: existing plaintext tokens.
        return value

    key = _get_key_bytes()
    if not key:
        raise TokenCryptoError("Encrypted token cannot be decrypted without TOKEN_ENCRYPTION_KEY.")

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


def encrypt_token_if_enabled(value: str) -> str:
    if not isinstance(value, str) or not value:
        return value
    if is_encrypted_token(value):
        return value

    key = _get_key_bytes()
    if not key:
        # Backward compatibility: when key is not configured, keep plaintext behavior.
        return value

    aesgcm_cls = _get_aesgcm()
    iv = os.urandom(_TOKEN_IV_BYTES)
    payload = aesgcm_cls(key).encrypt(iv, value.encode("utf-8"), None)
    ciphertext = payload[:-_TOKEN_TAG_BYTES]
    auth_tag = payload[-_TOKEN_TAG_BYTES:]
    return f"{TOKEN_ENCRYPTION_PREFIX}{iv.hex()}:{auth_tag.hex()}:{ciphertext.hex()}"
