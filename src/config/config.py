import os
from pathlib import Path

# Get the current directory
CURRENT_DIR = Path(__file__).resolve().parent.parent.parent
print(f"Current directory: {CURRENT_DIR}")


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


def get_google_credential_env():
    payload = {
        "installed": {
            "client_id": os.environ.get("GOOGLE_CALENDAR_CLIENT_ID"),
            "project_id": os.environ.get("GOOGLE_CALENDAR_PROJECT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": os.environ.get("GOOGLE_CALENDAR_CLIENT_SECRET"),
            "redirect_uris": ["http://localhost"],
        }
    }
    return payload


def generate_uuid_config(user_uuid: str):
    """
    Dynamically generate CONFIG with user's UUID
    """
    LOCAL_NOTION_SETTINGS_PATH = os.environ.get("LOCAL_NOTION_SETTINGS_PATH", CURRENT_DIR / "token/notion_setting.json")
    LOCAL_CLIENT_SECRET_PATH = os.environ.get("LOCAL_CLIENT_SECRET_PATH", CURRENT_DIR / "token/client_secret.json")
    LOCAL_CREDENTIALS_PATH = os.environ.get("LOCAL_CREDENTIALS_PATH", CURRENT_DIR / "token/token.json")
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
    S3_NOTION_SETTINGS_PATH = os.environ.get("S3_NOTION_SETTINGS_PATH")
    S3_CREDENTIALS_PATH = os.environ.get("S3_CREDENTIALS_PATH")
    S3_CLIENT_SECRET_PATH = os.environ.get("S3_CLIENT_SECRET_PATH")
    USE_ENV_GOOGLE_SECRET = os.environ.get("USE_ENV_GOOGLE_SECRET", "false").lower() == "true"

    if not user_uuid:
        # use local
        return {
            "local_notion_settings_path": Path(LOCAL_NOTION_SETTINGS_PATH),
            "local_client_secret_path": Path(LOCAL_CLIENT_SECRET_PATH),
            "local_credentials_path": Path(LOCAL_CREDENTIALS_PATH),
            "use_env_google_secret": USE_ENV_GOOGLE_SECRET,
        }
    if not S3_BUCKET_NAME:
        raise SettingError(
            f"UUID: {user_uuid}, S3_BUCKET_NAME is not set. Please set it in your environment variables."
        )
    if not S3_NOTION_SETTINGS_PATH:
        raise SettingError(
            f"UUID: {user_uuid}, S3_NOTION_SETTINGS_PATH is not set. Please set it in your environment variables."
        )
    if not S3_CREDENTIALS_PATH:
        raise SettingError(
            f"UUID: {user_uuid}, S3_CREDENTIALS_PATH is not set. Please set it in your environment variables."
        )
    if not S3_CLIENT_SECRET_PATH:
        raise SettingError(
            f"UUID: {user_uuid}, S3_CLIENT_SECRET_PATH is not set. Please set it in your environment variables."
        )
    return {
        "s3_bucket_name": S3_BUCKET_NAME,
        "s3_key_notion": f"{user_uuid}/{S3_NOTION_SETTINGS_PATH}",
        "s3_credentials_path": f"{user_uuid}/{S3_CREDENTIALS_PATH}",
        "s3_client_secret_path": S3_CLIENT_SECRET_PATH,
        "has_s3_notion": bool(S3_BUCKET_NAME and S3_NOTION_SETTINGS_PATH),
        "has_s3_google": bool(S3_BUCKET_NAME and S3_CREDENTIALS_PATH),
        "use_env_google_secret": USE_ENV_GOOGLE_SECRET,
    }


if __name__ == "__main__":
    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold green]🔧 Configuration Source")
    pprint(generate_uuid_config("test"), max_depth=3)
