import sys
import argparse
import json
from pathlib import Path
from google.auth.exceptions import RefreshError

# Ensure this module can import sibling packages when run as a script
sys.path.append(str(Path(__file__).resolve().parent))

from config.config import generate_config  # noqa: E402
from config.mapping_domain_config import (  # noqa: E402
    MappingDomainConfig,
    SettingError as MappingDomainSettingError,
    apply_date_range,
)
from notion.notion_service import NotionService  # noqa: E402
from notion.notion_token import NotionToken  # noqa: E402
from gcal.gcal_token import (  # noqa: E402
    GoogleToken,
    SettingError as GoogleTokenSettingError,
)
from gcal.gcal_service import GoogleService, SettingError as GoogleSettingError  # noqa: E402
from sync.contracts import (  # noqa: E402
    StaleExecutionError,
    build_sync_result,
    get_result_message,
    get_result_status,
    is_retryable_result,
)
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


def _run_source(
    args,
    source_setting,
    notion_token,
    google_token,
    logger,
    mutation_guard,
):
    notion_service = NotionService(notion_token, source_setting, logger)
    google_service = GoogleService(
        source_setting,
        google_token,
        logger,
        mutation_guard=mutation_guard,
    )
    google_service.validate_calendar_access()

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

    if args.timestamp:
        _apply_date_range_override(source_setting, args.timestamp[0], args.timestamp[1], logger)
    elif args.notion:
        _apply_date_range_override(source_setting, args.notion[0], args.notion[1], logger)

    return sync.project_notion_to_google_calendar(
        user_setting=source_setting,
        notion_service=notion_service,
        google_service=google_service,
    )


def _aggregate_source_results(source_results):
    summaries = []
    errors = []
    retryable_failure_count = 0
    failure_count = 0
    for source_id, result in source_results:
        retryable = is_retryable_result(result)
        retryable_failure_count += int(retryable)
        message = get_result_message(result)
        error_code = message.get("error_code") if isinstance(message, dict) else None
        source_status_code = int((result or {}).get("statusCode", 500))
        source_errors = message.get("errors") if isinstance(message, dict) else None
        has_task_errors = bool(source_errors) and not message.get("capacity_limited", False)
        source_failed = source_status_code >= 400 or get_result_status(result) == "sync_error" or has_task_errors
        failure_count += int(source_failed)
        summaries.append(
            {
                "source_id": source_id,
                "status_code": source_status_code,
                "status": get_result_status(result),
                "error_code": error_code,
                "retriable": retryable,
            }
        )
        if isinstance(message, dict) and isinstance(source_errors, list):
            for error in source_errors:
                if isinstance(error, dict):
                    errors.append({**error, "source_id": source_id})

    source_count = len(source_results)
    status_code = 500 if retryable_failure_count else (409 if failure_count else 200)
    return build_sync_result(
        status_code,
        "sync_error" if failure_count else "sync_success",
        {
            "source_count": source_count,
            "success_count": source_count - failure_count,
            "failure_count": failure_count,
            "source_summaries": summaries,
            "errors": errors,
            "retriable": retryable_failure_count > 0,
        },
    )


def main(uuid: str | None = None, execution: dict | None = None) -> dict:
    logger = get_logger(__name__)

    try:
        config = generate_config(uuid)
        mapping_config = MappingDomainConfig(
            config,
            logger,
            execution_fence=execution,
        )
        source_settings = mapping_config.get()
        notion_token = NotionToken(config, logger).get()
        google_token = GoogleToken(config, logger)
        if execution is not None:
            google_token.assert_admission_binding(
                source_settings[0]["admission_started_at_ms"]
            )
    except RefreshError as e:
        logger.error(f"Google RefreshError during initialization: {e}", exc_info=True)
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
            {"error_code": "sync_configuration_invalid", "retriable": False},
        )
    except GoogleTokenSettingError:
        logger.exception("Google provider binding is not valid for this sync execution")
        return build_sync_result(
            409,
            "sync_error",
            {"error_code": "sync_provider_binding_stale", "retriable": False},
        )
    except Exception:
        logger.exception("Error loading mapping-domain configuration or tokens")
        return build_sync_result(
            500,
            "sync_error",
            {"error_code": "service_initialization_error", "retriable": True},
        )

    # Parse CLI args (safe for lambda - argv is just script name)
    try:
        args = _parse_args()
        logger.debug(f"Parsed arguments: {args}")
    except Exception as e:
        logger.error(f"Error parsing arguments: {e}")

    source_results = []
    for source_setting in source_settings:
        source_id = source_setting["source_id"]
        try:
            def mutation_guard(setting=source_setting):
                try:
                    mapping_config.revalidate_source(setting)
                    google_token.assert_current_binding()
                except (MappingDomainSettingError, GoogleTokenSettingError) as exc:
                    raise StaleExecutionError(
                        "Sync execution is no longer authoritative."
                    ) from exc

            result = _run_source(
                args,
                source_setting,
                notion_token,
                google_token,
                logger,
                mutation_guard,
            )
        except GoogleSettingError:
            logger.exception("Source Calendar mapping is not sync-ready: source_id=%s", source_id)
            result = build_sync_result(
                409,
                "sync_error",
                {"error_code": "source_calendar_mapping_invalid", "retriable": False},
            )
        except Exception:
            logger.exception("Source sync failed during initialization or execution: source_id=%s", source_id)
            result = build_sync_result(
                500,
                "sync_error",
                {"error_code": "source_sync_failed", "retriable": True},
            )
        source_results.append((source_id, result))
    return _aggregate_source_results(source_results)


if __name__ == "__main__":
    # python -m src.main
    UUID = ""  # Replace with your UUID or leave empty for local
    response = main(UUID)
    print(json.dumps(response, indent=2))
