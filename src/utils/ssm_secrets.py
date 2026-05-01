import os
from typing import Any


_SSM_CLIENT: Any | None = None
_PARAMETER_CACHE: dict[str, str] = {}


class SSMSecretError(ValueError):
    """Raised when SSM secret resolution fails."""


def _resolve_region() -> str:
    region = (os.getenv("APP_REGION") or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "").strip()
    if not region:
        raise SSMSecretError(
            "AWS region is required for SSM secret resolution. Set APP_REGION, AWS_REGION, or AWS_DEFAULT_REGION."
        )
    return region


def _get_ssm_client():
    global _SSM_CLIENT
    if _SSM_CLIENT is None:
        # Lazy import to avoid loading boto3 unless SSM resolution is needed.
        import boto3

        _SSM_CLIENT = boto3.client("ssm", region_name=_resolve_region())
    return _SSM_CLIENT


def get_ssm_parameter(name: str) -> str:
    parameter_name = (name or "").strip()
    if not parameter_name:
        raise SSMSecretError("SSM parameter name is required.")

    if parameter_name in _PARAMETER_CACHE:
        return _PARAMETER_CACHE[parameter_name]

    try:
        response = _get_ssm_client().get_parameter(Name=parameter_name, WithDecryption=True)
        value = response["Parameter"]["Value"]
    except SSMSecretError:
        raise
    except Exception as exc:
        raise SSMSecretError(f"Failed to resolve SSM parameter '{parameter_name}'.") from exc

    _PARAMETER_CACHE[parameter_name] = value
    return value
