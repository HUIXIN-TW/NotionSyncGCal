import os
import sys
import logging


def get_logger(name: str, log_file) -> logging.Logger:
    """Get a logger that always logs to stdout with a simple formatter (for Lambda/CloudWatch)."""
    # DEBUG with event details
    # INFO with calendar level summary
    # WARNING for recoverable errors
    # ERROR for non-recoverable errors
    logger = logging.getLogger(name)
    env = os.environ.get("ENVIRONMENT", "production")
    # print(f"environment: {env} in file: {__file__}, log_file: {log_file}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if env.lower() == "production":
            handler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            handler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    return logger


__all__ = ["get_logger"]
