#!/usr/bin/env python3
"""Local sync invocation helper for APP_MODE=cloud and APP_MODE=local.

The shell runner validates and loads environment variables before calling this
script. This helper does not print secret environment values.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Make repo root and src importable regardless of cwd.
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent
_SRC = _REPO_ROOT / "src"
for _p in (_REPO_ROOT, _SRC):
    p_str = str(_p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)


def _parse_args():
    parser = argparse.ArgumentParser(description="Invoke Notion-GCal sync locally with explicit APP_MODE.")
    parser.add_argument("--mode", required=True, choices=("cloud", "local"), help="Invocation mode")
    parser.add_argument("--uuid", help="User UUID to sync. Required in cloud mode.")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Read and validate cloud mapping-domain configuration without loading provider tokens or running sync.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable DEBUG-level logging")
    return parser.parse_args()


def _require_env(names: list[str]):
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        print("ERROR: Required environment variables are not set:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}", file=sys.stderr)
        sys.exit(1)


def _set_and_validate_mode(mode: str):
    current_mode = os.environ.get("APP_MODE")
    if current_mode and current_mode != mode:
        print(f"ERROR: APP_MODE is '{current_mode}', but --mode is '{mode}'.", file=sys.stderr)
        sys.exit(1)
    os.environ["APP_MODE"] = mode


def _build_sqs_event(uuid: str) -> dict:
    """Build an SQS-shaped Lambda event matching the handler contract."""
    return {
        "Records": [
            {
                "messageId": "local-dev-invocation",
                "receiptHandle": "local",
                "body": json.dumps({"uuid": uuid, "trigger_by": "local", "source": "local-dev"}),
                "eventSource": "aws:sqs",
                "awsRegion": os.environ.get("APP_REGION") or os.environ.get("AWS_REGION"),
            }
        ]
    }


def _fake_context(uuid: str):
    return type(
        "FakeContext",
        (),
        {
            "function_name": "local-dev-fn-notion-sync-gcal",
            "aws_request_id": f"local-{uuid[:8]}",
            "log_stream_name": "/aws/lambda/local-dev",
            "log_group_name": "/aws/lambda/local-dev",
            "memory_limit_in_mb": 512,
        },
    )()


def _call_with_isolated_argv(fn, *args, **kwargs):
    original_argv = sys.argv[:]
    sys.argv = [original_argv[0] if original_argv else __file__]
    try:
        return fn(*args, **kwargs)
    finally:
        sys.argv = original_argv



def _build_safe_config_summary(uuid: str, source_settings: list[dict]) -> dict:
    """Return a secret-free summary of expanded mapping-domain configuration."""
    sources = []
    for setting in source_settings:
        sources.append(
            {
                "source_id": setting["source_id"],
                "database_id": setting["database_id"],
                "timezone": setting["timezone"],
                "timecode": setting["timecode"],
                "go_back_days": setting["goback_days"],
                "go_forward_days": setting["goforward_days"],
                "default_calendar_name": setting["gcal_default_name"],
                "calendar_names": list(setting["gcal_name_dict"].keys()),
                "property_bindings": sorted(setting["page_property"].keys()),
            }
        )
    return {
        "statusCode": 200,
        "body": {
            "status": "config_valid",
            "message": {
                "read_only": True,
                "uuid": uuid,
                "source_count": len(sources),
                "sources": sources,
            },
        },
    }


def _check_cloud_config(uuid: str, logger: logging.Logger):
    """Read/validate mapping-domain config only; never load provider tokens or run sync."""
    if not uuid:
        print("ERROR: --uuid is required in cloud mode.", file=sys.stderr)
        sys.exit(1)

    _set_and_validate_mode("cloud")
    _require_env(["DYNAMODB_MAPPING_DOMAIN_TABLE", "APP_REGION"])

    from config.config import generate_config
    from config.mapping_domain_config import MappingDomainConfig

    logger.info("Mode: cloud read-only configuration check")
    logger.info("UUID: %s", uuid)
    source_settings = MappingDomainConfig(generate_config(uuid), logger).get()
    return _build_safe_config_summary(uuid, source_settings)

def _invoke_cloud(uuid: str, logger: logging.Logger):
    if not uuid:
        print("ERROR: --uuid is required in cloud mode.", file=sys.stderr)
        sys.exit(1)

    _set_and_validate_mode("cloud")
    _require_env(
        [
            "DYNAMODB_USER_TABLE",
            "DYNAMODB_MAPPING_DOMAIN_TABLE",
            "DYNAMODB_SYNC_LOGS_TABLE",
            "DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE",
            "DYNAMODB_NOTION_OAUTH_TOKEN_TABLE",
            "TOKEN_ENCRYPTION_KEY_SSM_PATH",
            "GOOGLE_CALENDAR_CLIENT_ID",
            "GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH",
            "APP_REGION",
        ]
    )

    logger.info("Mode: cloud")
    logger.info("UUID: %s", uuid)

    try:
        from lambda_function import lambda_handler
    except ImportError as exc:
        print(f"ERROR: Could not import lambda_function: {exc}", file=sys.stderr)
        print("       Ensure you are running from the repo root via uv run.", file=sys.stderr)
        sys.exit(1)

    logger.info("Invoking lambda_handler with local SQS-shaped event.")
    return _call_with_isolated_argv(lambda_handler, _build_sqs_event(uuid), _fake_context(uuid))


def _invoke_local(logger: logging.Logger):
    _set_and_validate_mode("local")
    _require_env(
        [
            "NOTION_TOKEN",
            "GOOGLE_CALENDAR_CLIENT_ID",
            "GOOGLE_CALENDAR_CLIENT_SECRET",
            "GOOGLE_CALENDAR_REFRESH_TOKEN",
        ]
    )

    logger.info("Mode: local")
    logger.info("Invoking src.main.main(uuid=None).")

    try:
        from src.main import main as run_sync
    except ImportError as exc:
        print(f"ERROR: Could not import src.main: {exc}", file=sys.stderr)
        print("       Ensure you are running from the repo root via uv run.", file=sys.stderr)
        sys.exit(1)

    return _call_with_isolated_argv(run_sync, uuid=None)


def _result_failed(result) -> bool:
    if result is None:
        return True
    if isinstance(result, dict):
        status_code = result.get("statusCode")
        if isinstance(status_code, int):
            return status_code >= 400
        return "error" in result
    return False


def main():
    args = _parse_args()

    if args.mode == "local" and args.uuid:
        print("ERROR: --uuid is only supported in cloud mode.", file=sys.stderr)
        sys.exit(1)
    if args.check_config and args.mode != "cloud":
        print("ERROR: --check-config is supported only in cloud mode.", file=sys.stderr)
        sys.exit(1)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    try:
        if args.mode == "cloud":
            result = _check_cloud_config(args.uuid, logger) if args.check_config else _invoke_cloud(args.uuid, logger)
        else:
            result = _invoke_local(logger)
    except Exception as exc:
        logger.exception("Local sync invocation failed.")
        print(f"\n[FAILURE] Sync invocation raised {exc.__class__.__name__}.", file=sys.stderr)
        sys.exit(1)

    print("\n=== Configuration Check Result ===" if args.check_config else "\n=== Sync Result ===")
    print(json.dumps(result, indent=2, default=str))

    if _result_failed(result):
        print("\n[FAILURE] Sync returned an error result.", file=sys.stderr)
        sys.exit(1)

    print(
        "\n[SUCCESS] Configuration is valid and no provider sync was run."
        if args.check_config
        else "\n[SUCCESS] Sync completed."
    )


if __name__ == "__main__":
    main()
