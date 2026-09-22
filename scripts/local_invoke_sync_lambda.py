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
    parser.add_argument(
        "--check-provider-match",
        action="store_true",
        help="Read Notion/Google provider data and verify existing GCal Event Id matches without sync mutations.",
    )
    parser.add_argument(
        "--canary-page-id",
        help=(
            "Cloud only: force one existing Notion page -> its existing Google event "
            "using the normal sync update path."
        ),
    )
    parser.add_argument(
        "--confirm-canary-page-id",
        help="Must exactly match --canary-page-id before the one-pair provider mutation can run.",
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
                "property_ids": dict(sorted(setting["page_property"].items())),
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


def _check_cloud_provider_match(uuid: str, logger: logging.Logger):
    """Verify existing Notion GCal Event Id values resolve to provider events without sync mutations."""
    if not uuid:
        print("ERROR: --uuid is required in cloud mode.", file=sys.stderr)
        sys.exit(1)

    _set_and_validate_mode("cloud")
    _require_env(
        [
            "DYNAMODB_MAPPING_DOMAIN_TABLE",
            "DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE",
            "DYNAMODB_NOTION_OAUTH_TOKEN_TABLE",
            "TOKEN_ENCRYPTION_KEY_SSM_PATH",
            "GOOGLE_CALENDAR_CLIENT_ID",
            "GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH",
            "APP_REGION",
        ]
    )

    from collections import Counter

    from config.config import generate_config
    from config.mapping_domain_config import MappingDomainConfig
    from gcal.gcal_service import GoogleService
    from gcal.gcal_token import GoogleToken
    from notion.notion_properties import get_rich_text
    from notion.notion_service import NotionService
    from notion.notion_token import NotionToken

    logger.info("Mode: cloud provider match check (no sync mutations)")
    logger.info("UUID: %s", uuid)

    config = generate_config(uuid)
    source_settings = MappingDomainConfig(config, logger).get()
    notion_token = NotionToken(config, logger).get()
    google_token = GoogleToken(config, logger)

    source_summaries = []
    total_with_event_id = 0
    total_matched = 0
    total_missing = 0
    total_duplicates = 0

    for setting in source_settings:
        notion_service = NotionService(notion_token, setting, logger)
        google_service = GoogleService(setting, google_token, logger)

        _, notion_tasks = notion_service.get_notion_task()
        google_events = google_service.get_gcal_event()

        event_id_property = setting["page_property"]["GCal_EventId_Notion_Name"]
        notion_event_ids = [
            event_id
            for task in notion_tasks
            if (event_id := get_rich_text(task.get("properties", {}), event_id_property))
        ]
        google_event_ids = {
            event.get("id")
            for event in google_events
            if isinstance(event.get("id"), str) and event.get("id")
        }

        counts = Counter(notion_event_ids)
        duplicate_event_ids = sum(1 for count in counts.values() if count > 1)
        matched = sum(1 for event_id in notion_event_ids if event_id in google_event_ids)
        missing = len(notion_event_ids) - matched

        total_with_event_id += len(notion_event_ids)
        total_matched += matched
        total_missing += missing
        total_duplicates += duplicate_event_ids

        source_summaries.append(
            {
                "source_id": setting["source_id"],
                "notion_task_count": len(notion_tasks),
                "google_event_count": len(google_events),
                "notion_tasks_with_event_id": len(notion_event_ids),
                "matched_event_ids": matched,
                "missing_event_ids": missing,
                "duplicate_notion_event_ids": duplicate_event_ids,
            }
        )

    if total_with_event_id == 0:
        return {
            "statusCode": 409,
            "body": {
                "status": "provider_match_not_proven",
                "message": {
                    "read_only_provider_data": True,
                    "oauth_token_refresh_may_persist": True,
                    "reason": "No Notion task with GCal Event Id was found in the configured sync window.",
                    "source_count": len(source_summaries),
                    "sources": source_summaries,
                },
            },
        }

    status_code = 200 if total_missing == 0 and total_duplicates == 0 else 409
    return {
        "statusCode": status_code,
        "body": {
            "status": "provider_match_valid" if status_code == 200 else "provider_match_conflict",
            "message": {
                "read_only_provider_data": True,
                "oauth_token_refresh_may_persist": True,
                "source_count": len(source_summaries),
                "notion_tasks_with_event_id": total_with_event_id,
                "matched_event_ids": total_matched,
                "missing_event_ids": total_missing,
                "duplicate_notion_event_ids": total_duplicates,
                "sources": source_summaries,
            },
        },
    }


class _ScopedNotionService:
    """Delegate all writes to the real service but expose exactly one task to the sync algorithm."""

    def __init__(self, delegate, page):
        self._delegate = delegate
        self._page = page

    def get_notion_task(self):
        return ({"action": "canary_get_notion_task"}, [self._page])

    def __getattr__(self, name):
        return getattr(self._delegate, name)


class _ScopedGoogleService:
    """Delegate all writes to the real service but expose exactly one event to the sync algorithm."""

    def __init__(self, delegate, event):
        self._delegate = delegate
        self._event = event

    def get_gcal_event(self):
        return [self._event]

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def _normalize_notion_id(value: str | None) -> str:
    return (value or "").replace("-", "").lower()


def _run_cloud_canary(uuid: str, page_id: str, confirm_page_id: str, logger: logging.Logger):
    """Run one explicitly confirmed existing Notion -> Google update through the existing sync algorithm."""
    if not uuid:
        print("ERROR: --uuid is required in cloud mode.", file=sys.stderr)
        sys.exit(1)
    if not page_id or not confirm_page_id or page_id != confirm_page_id:
        print(
            "ERROR: --canary-page-id and --confirm-canary-page-id must both be set to the same page ID.",
            file=sys.stderr,
        )
        sys.exit(1)

    _set_and_validate_mode("cloud")
    _require_env(
        [
            "DYNAMODB_MAPPING_DOMAIN_TABLE",
            "DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE",
            "DYNAMODB_NOTION_OAUTH_TOKEN_TABLE",
            "TOKEN_ENCRYPTION_KEY_SSM_PATH",
            "GOOGLE_CALENDAR_CLIENT_ID",
            "GOOGLE_CALENDAR_CLIENT_SECRET_SSM_PATH",
            "APP_REGION",
        ]
    )

    from config.config import generate_config
    from config.mapping_domain_config import MappingDomainConfig
    from gcal.gcal_service import GoogleService
    from gcal.gcal_token import GoogleToken
    from notion.notion_properties import get_checkbox, get_rich_text, get_select
    from notion.notion_service import NotionService
    from notion.notion_token import NotionToken
    from sync import sync

    logger.warning("Running explicitly confirmed one-pair Notion -> Google provider canary.")
    logger.info("UUID: %s", uuid)
    logger.info("Canary Notion page ID: %s", page_id)

    config = generate_config(uuid)
    source_settings = MappingDomainConfig(config, logger).get()
    notion_token = NotionToken(config, logger).get()
    google_token = GoogleToken(config, logger)

    for setting in source_settings:
        notion_service = NotionService(notion_token, setting, logger)
        page = notion_service.client.pages.retrieve(page_id=page_id)
        parent_database_id = (page.get("parent") or {}).get("database_id")
        if _normalize_notion_id(parent_database_id) != _normalize_notion_id(setting["database_id"]):
            continue

        page_properties = page.get("properties", {})
        event_id = get_rich_text(
            page_properties,
            setting["page_property"]["GCal_EventId_Notion_Name"],
        )
        if not event_id:
            return {
                "statusCode": 409,
                "body": {
                    "status": "canary_refused",
                    "message": "Selected Notion page has no GCal Event Id; refusing create-path canary.",
                },
            }

        if get_checkbox(
            page_properties,
            setting["page_property"]["Delete_Notion_Name"],
        ):
            return {
                "statusCode": 409,
                "body": {
                    "status": "canary_refused",
                    "message": "Selected Notion page is marked for deletion; refusing destructive canary.",
                },
            }

        calendar_name = get_select(
            page_properties,
            setting["page_property"]["GCal_Name_Notion_Name"],
        ) or setting["gcal_default_name"]
        expected_calendar_id = setting["gcal_name_dict"].get(calendar_name)
        if not expected_calendar_id:
            return {
                "statusCode": 409,
                "body": {
                    "status": "canary_refused",
                    "message": "Selected Notion page references an unmapped Calendar.",
                },
            }

        google_service = GoogleService(setting, google_token, logger)
        google_events_before = google_service.get_gcal_event()
        matching_events = [event for event in google_events_before if event.get("id") == event_id]
        if len(matching_events) != 1:
            return {
                "statusCode": 409,
                "body": {
                    "status": "canary_refused",
                    "message": "Expected exactly one existing Google event for the selected GCal Event Id.",
                },
            }

        existing_event = matching_events[0]
        current_calendar_id = (existing_event.get("organizer") or {}).get("email")
        if current_calendar_id != expected_calendar_id:
            return {
                "statusCode": 409,
                "body": {
                    "status": "canary_refused",
                    "message": "Selected pair would move Calendars; choose a pair already in its configured Calendar.",
                },
            }

        result = sync.force_update_google_event_by_notion_task_and_ignore_time(
            user_setting=setting,
            notion_service=_ScopedNotionService(notion_service, page),
            google_service=_ScopedGoogleService(google_service, existing_event),
        )
        if int((result or {}).get("statusCode", 500)) >= 400:
            return result

        google_events_after = google_service.get_gcal_event()
        matching_after = [event for event in google_events_after if event.get("id") == event_id]
        event_count_unchanged = len(google_events_after) == len(google_events_before)
        same_event_preserved = len(matching_after) == 1
        if not event_count_unchanged or not same_event_preserved:
            return {
                "statusCode": 409,
                "body": {
                    "status": "canary_verification_failed",
                    "message": {
                        "same_event_preserved": same_event_preserved,
                        "google_event_count_before": len(google_events_before),
                        "google_event_count_after": len(google_events_after),
                    },
                },
            }

        return {
            "statusCode": 200,
            "body": {
                "status": "canary_sync_valid",
                "message": {
                    "scope": "one_existing_pair",
                    "direction": "notion_to_google",
                    "source_id": setting["source_id"],
                    "notion_page_id": page_id,
                    "event_id_suffix": event_id[-8:],
                    "calendar_name": calendar_name,
                    "same_event_preserved": True,
                    "google_event_count_before": len(google_events_before),
                    "google_event_count_after": len(google_events_after),
                    "sync_status": (result.get("body") or {}).get("status"),
                },
            },
        }

    return {
        "statusCode": 404,
        "body": {
            "status": "canary_refused",
            "message": "Selected Notion page does not belong to any active configured Task source.",
        },
    }


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
    if args.check_provider_match and args.mode != "cloud":
        print("ERROR: --check-provider-match is supported only in cloud mode.", file=sys.stderr)
        sys.exit(1)
    if args.check_config and args.check_provider_match:
        print("ERROR: --check-config and --check-provider-match are mutually exclusive.", file=sys.stderr)
        sys.exit(1)
    if (args.canary_page_id or args.confirm_canary_page_id) and args.mode != "cloud":
        print("ERROR: provider canary is supported only in cloud mode.", file=sys.stderr)
        sys.exit(1)
    if (args.canary_page_id or args.confirm_canary_page_id) and (args.check_config or args.check_provider_match):
        print("ERROR: provider canary cannot be combined with read-only check modes.", file=sys.stderr)
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
            if args.check_config:
                result = _check_cloud_config(args.uuid, logger)
            elif args.check_provider_match:
                result = _check_cloud_provider_match(args.uuid, logger)
            elif args.canary_page_id or args.confirm_canary_page_id:
                result = _run_cloud_canary(
                    args.uuid,
                    args.canary_page_id,
                    args.confirm_canary_page_id,
                    logger,
                )
            else:
                result = _invoke_cloud(args.uuid, logger)
        else:
            result = _invoke_local(logger)
    except Exception as exc:
        logger.exception("Local sync invocation failed.")
        print(f"\n[FAILURE] Sync invocation raised {exc.__class__.__name__}.", file=sys.stderr)
        sys.exit(1)

    if args.check_config:
        heading = "\n=== Configuration Check Result ==="
    elif args.check_provider_match:
        heading = "\n=== Provider Match Check Result ==="
    elif args.canary_page_id or args.confirm_canary_page_id:
        heading = "\n=== One-Pair Provider Canary Result ==="
    else:
        heading = "\n=== Sync Result ==="
    print(heading)
    print(json.dumps(result, indent=2, default=str))

    if _result_failed(result):
        print("\n[FAILURE] Sync returned an error result.", file=sys.stderr)
        sys.exit(1)

    if args.check_config:
        success_message = "\n[SUCCESS] Configuration is valid and no provider sync was run."
    elif args.check_provider_match:
        success_message = "\n[SUCCESS] Existing GCal Event Id values matched provider events; no sync mutations ran."
    elif args.canary_page_id or args.confirm_canary_page_id:
        success_message = "\n[SUCCESS] One existing provider pair was updated without creating a duplicate event."
    else:
        success_message = "\n[SUCCESS] Sync completed."
    print(success_message)


if __name__ == "__main__":
    main()
