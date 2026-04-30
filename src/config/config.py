import os
from pathlib import Path
from utils.logging_utils import get_logger  # noqa: E402

CURRENT_DIR = Path(__file__).resolve().parent.parent.parent
logger = get_logger(__name__)


class ConfigError(Exception):
    """Raised when APP_MODE or required config values are missing or invalid."""


def generate_config(user_uuid: str = None, app_mode: str = None):
    """Generate a config dict based on APP_MODE.

    APP_MODE=cloud  — DynamoDB-backed path; uuid is required.
    APP_MODE=local  — env-var + local JSON config path; uuid is not required.

    APP_MODE must be set explicitly; mode is never inferred from uuid.
    token/*.json paths are not supported.
    """
    resolved_mode = app_mode or os.environ.get("APP_MODE")
    logger.debug(f"APP_MODE: {resolved_mode}, uuid: {user_uuid}")

    if not resolved_mode:
        raise ConfigError("APP_MODE environment variable is required. Set APP_MODE=cloud or APP_MODE=local.")

    if resolved_mode == "cloud":
        if not user_uuid:
            raise ConfigError("uuid is required when APP_MODE=cloud.")
        return {
            "mode": "cloud",
            "uuid": user_uuid,
        }

    if resolved_mode == "local":
        return {
            "mode": "local",
            "notion_setting_path": CURRENT_DIR / "config" / "local.notion-setting.json",
        }

    raise ConfigError(f"Unknown APP_MODE '{resolved_mode}'. Expected 'cloud' or 'local'.")


if __name__ == "__main__":
    from rich.console import Console
    from rich.pretty import pprint

    # python -m config.config  (APP_MODE must be set in the shell)
    console = Console()
    console.rule("[bold green]🔧 Configuration Source")
    pprint(generate_config(), max_depth=3)
