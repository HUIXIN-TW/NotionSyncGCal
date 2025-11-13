import os
from pathlib import Path
from utils.logging_utils import get_logger  # noqa: E402

# Get the current directory
CURRENT_DIR = Path(__file__).resolve().parent.parent.parent
logger = get_logger(__name__, os.getenv("LOG_FILE_PATH"))

current_dir = Path(__file__).parent.resolve()
logger.debug(f"Current directory: {CURRENT_DIR}")


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


def generate_config(user_uuid: str):
    """Dynamically generate CONFIG based on whether UUID is provided.

    - If user_uuid is provided: use S3 paths scoped by that UUID and DynamoDB tables
    - If user_uuid is empty: use local token files under repo 'token/'
    """
    mode = "local" if not user_uuid else "serverless"
    logger.debug(f"Configuration mode: {mode}, UUID: {user_uuid}")

    if mode == "serverless":
        S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
        S3_NOTION_CONFIG_PATH = os.environ.get("S3_NOTION_CONFIG_PATH")
        return {
            "mode": mode,
            "uuid": user_uuid,
            "s3_bucket_name": S3_BUCKET_NAME,
            "s3_key_notion_config": f"{user_uuid}/{S3_NOTION_CONFIG_PATH}",
        }
    else:
        LOCAL_NOTION_SETTINGS_PATH = os.environ.get(
            "LOCAL_NOTION_SETTINGS_PATH", CURRENT_DIR / "token/notion_setting.json"
        )
        LOCAL_GOOGLE_CLIENT_SECRET_PATH = os.environ.get(
            "LOCAL_GOOGLE_CLIENT_SECRET_PATH", CURRENT_DIR / "token/client_secret.json"
        )
        LOCAL_GOOGLE_TOKEN_PATH = os.environ.get("LOCAL_GOOGLE_TOKEN_PATH", CURRENT_DIR / "token/token.json")
        return {
            "mode": mode,
            "local_notion_settings_path": Path(LOCAL_NOTION_SETTINGS_PATH),
            "local_google_client_secret_path": Path(LOCAL_GOOGLE_CLIENT_SECRET_PATH),
            "local_google_token_path": Path(LOCAL_GOOGLE_TOKEN_PATH),
        }


if __name__ == "__main__":
    from rich.console import Console
    from rich.pretty import pprint

    # python -m config.config
    console = Console()
    console.rule("[bold green]🔧 Configuration Source")
    pprint(generate_config(""), max_depth=3)
