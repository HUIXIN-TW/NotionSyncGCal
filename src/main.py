import sys
import argparse
import json
from pathlib import Path

from google.auth.exceptions import RefreshError

sys.path.append(str(Path(__file__).resolve().parent))

from config.config import generate_config  # noqa: E402
from config.mapping_domain_config import (  # noqa: E402
    MappingDomainConfig,
    SettingError as MappingDomainSettingError,
    apply_date_range,
)
from notion.notion_service import NotionService  # noqa: E402
from notion.notion_token import (  # noqa: E402
    NotionToken,
    SettingError as NotionTokenSettingError,
)
from gcal.gcal_token import (  # noqa: E402
    GoogleToken,
    SettingError as GoogleTokenSettingError,
)
from gcal.gcal_service import GoogleService  # noqa: E402
from sync.contracts import build_sync_result, is_retryable_result  # noqa: E402
from utils.logging_utils import get_logger  # noqa: E402


def _parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Welcome to Notion-Google Calendar Sync CLI!")
    parser.add_argument(
        "-x",
        "--test-connection",
        action="store_true",
        help="Test connections to Notion and Google Calendar services",
    )
    parser.add_argument(
        "-t",
        "--timestamp",
        nargs=2,
        type=int,
        help="Update Notion Task and Google Calendar by timestamp [start end]",
    )
    parser.add_argument(
        "-g",
        "--google",
        nargs=2,
        type=int,
        help="Force: Update Notion Task from Google Calendar [start end]",
    )
    parser.add_argument(
        "-n",
        "--notion",
        nargs=2,
        type=int,
        help="Force: Update Google Calendar from Notion Task [start end]",
    )
    return parser.parse_args(argv)


def _apply_date_range_override(
    user_setting: dict,
    goback_days: int,
    goforward_days: int,
    logger,
) -> None:
    apply_date_range(user_setting, goback_days, goforward_days)
    logger.debug(
        "Applied in-memory CLI date range override: " f"goback_days={goback_days}, goforward_days={goforward_days}"
    )


def _run_source(args, source_setting, notion_token, google_token, logger):
    if args.timestamp:
        _apply_date_range_override(
            source_setting,
            args.timestamp[0],
            args.timestamp[1],
            logger,
        )
    elif args.google:
        _apply_date_range_override(
            source_setting,
            args.google[0],
            args.google[1],
            logger,
        )
    elif args.notion:
        _apply_date_range_override(
            source_setting,
            args.notion[0],
            args.notion[1],
            logger,
        )

    notion_service = NotionService(notion_token, source_setting, logger)
    google_service = GoogleService(source_setting, google_token, logger)

    if args.test_connection:
        notion_connected = notion_service.test_connection()
        google_connected = google_service.test_connection()
        status_code = 200 if notion_connected and google_connected else 503
        return build_sync_result(
            status_code,
            "sync_success" if status_code == 200 else "sync_error",
            {
                "notion_connection": notion_connected,
                "google_connection": google_connected,
            },
        )

    from sync import sync

    if args.google:
        return sync.force_update_notion_tasks_by_google_event_and_ignore_time(
            user_setting=source_setting,
            notion_service=notion_service,
            google_service=google_service,
        )
    if args.notion:
        return sync.force_update_google_event_by_notion_task_and_ignore_time(
            user_setting=source_setting,
            notion_service=notion_service,
            google_service=google_service,
        )

    return sync.synchronize_notion_and_google_calendar(
        user_setting=source_setting,
        notion_service=notion_service,
        google_service=google_service,
        compare_time=True,
        should_update_notion_tasks=True,
        should_update_google_events=True,
    )


def _aggregate_source_results(source_results):
    if len(source_results) == 1:
        return source_results[0][1]

    summaries = []
    retryable = False
    failed = False
    for source_id, result in source_results:
        status_code = int((result or {}).get("statusCode", 500))
        body = (result or {}).get("body") or {}
        status = body.get("status", "sync_error")
        retryable = retryable or is_retryable_result(result)
        failed = failed or status_code >= 400 or status == "sync_error"
        summaries.append(
            {
                "source_id": source_id,
                "status_code": status_code,
                "status": status,
            }
        )

    return build_sync_result(
        500 if retryable else (409 if failed else 200),
        "sync_error" if failed else "sync_success",
        {
            "source_count": len(source_results),
            "source_summaries": summaries,
            "retriable": retryable,
        },
    )


def main(uuid: str | None = None) -> dict:
    logger = get_logger(__name__)

    try:
        config = generate_config(uuid)
        source_settings = MappingDomainConfig(config, logger).get()
        notion_token = NotionToken(config, logger).get()
        google_token = GoogleToken(config, logger)
    except RefreshError as exc:
        logger.error(
            f"Google RefreshError during initialization: {exc}",
            exc_info=True,
        )
        return build_sync_result(
            500,
            "sync_error",
            {"error_code": "google_refresh_error", "retriable": True},
        )
    except MappingDomainSettingError:
        logger.exception("Mapping-domain configuration is not sync-ready")
        return build_sync_result(
            409,
            "sync_error",
            {
                "error_code": "sync_configuration_invalid",
                "retriable": False,
            },
        )
    except (NotionTokenSettingError, GoogleTokenSettingError):
        logger.exception("Provider token configuration is invalid")
        return build_sync_result(
            409,
            "sync_error",
            {
                "error_code": "sync_provider_binding_invalid",
                "retriable": False,
            },
        )
    except Exception:
        logger.exception("Error loading mapping-domain configuration or tokens")
        return build_sync_result(
            500,
            "sync_error",
            {
                "error_code": "service_initialization_error",
                "retriable": True,
            },
        )

    try:
        args = _parse_args()
    except Exception:
        logger.exception("Error parsing CLI arguments")
        return build_sync_result(
            400,
            "sync_error",
            {
                "error_code": "invalid_cli_arguments",
                "retriable": False,
            },
        )

    source_results = []
    for source_setting in source_settings:
        source_id = source_setting["source_id"]
        try:
            result = _run_source(
                args,
                source_setting,
                notion_token,
                google_token,
                logger,
            )
        except Exception:
            logger.exception(
                "Source sync failed: source_id=%s",
                source_id,
            )
            result = build_sync_result(
                500,
                "sync_error",
                {
                    "error_code": "source_sync_failed",
                    "retriable": True,
                },
            )
        source_results.append((source_id, result))

    return _aggregate_source_results(source_results)


if __name__ == "__main__":
    UUID = ""
    response = main(UUID)
    print(json.dumps(response, indent=2))
