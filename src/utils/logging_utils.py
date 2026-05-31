import os
import sys
import logging

ENVIRONMENT_VAR = "ENVIRONMENT"
DEBUG_SYNC_ERROR_EXPOSURE_VAR = "EXPOSE_DEBUG_SYNC_ERRORS"
PRODUCTION_ENVIRONMENT = "production"
TRUTHY_FLAG_VALUES = frozenset({"1", "true", "yes", "on"})


def _normalized_env(key: str, default: str = "") -> str:
    value = os.environ.get(key, default)
    if value is None:
        value = default
    return str(value).strip().lower()


def is_production_environment() -> bool:
    current_environment = _normalized_env(ENVIRONMENT_VAR, PRODUCTION_ENVIRONMENT)
    return current_environment == PRODUCTION_ENVIRONMENT


def is_non_production() -> bool:
    return not is_production_environment()


def should_expose_debug_sync_error() -> bool:
    if is_production_environment():
        return False
    flag = _normalized_env(DEBUG_SYNC_ERROR_EXPOSURE_VAR)
    return flag in TRUTHY_FLAG_VALUES


def build_debug_exception_detail(exc: Exception) -> str | None:
    if not should_expose_debug_sync_error():
        return None
    return f"{type(exc).__name__}: {exc}"


def _get_log_level() -> int:
    if is_production_environment():
        return logging.INFO
    return logging.DEBUG


def get_logger(name: str) -> logging.Logger:
    """Get a logger that always logs to stdout with a simple formatter (for Lambda/CloudWatch)."""
    # DEBUG with event details
    # INFO with calendar level summary
    # WARNING for recoverable errors
    # ERROR for non-recoverable errors
    logger = logging.getLogger(name)
    log_level = _get_log_level()
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False

    for handler in logger.handlers:
        handler.setLevel(log_level)

    return logger


__all__ = [
    "get_logger",
    "is_non_production",
    "is_production_environment",
    "should_expose_debug_sync_error",
    "build_debug_exception_detail",
]
