import os
from pathlib import Path

# Get the current directory
CURRENT_DIR = Path(__file__).resolve().parent
print(f"Current directory: {CURRENT_DIR}")

def generate_uuid_config(user_uuid: str):
    """
    Dynamically generate CONFIG with user's UUID
    """
    return {
        "s3_bucket_name": os.environ.get("S3_BUCKET_NAME"),
        "s3_key_notion": f"{user_uuid}/{os.environ.get('S3_NOTION_SETTINGS_PATH')}",
        "s3_credentials_path": f"{user_uuid}/{os.environ.get('S3_CREDENTIALS_PATH')}",
        "s3_client_secret_path": os.environ.get("S3_CLIENT_SECRET_PATH"),
        "has_s3_notion": bool(os.environ.get("S3_BUCKET_NAME") and os.environ.get("S3_NOTION_SETTINGS_PATH")),
        "has_s3_google": bool(os.environ.get("S3_BUCKET_NAME") and os.environ.get("S3_CREDENTIALS_PATH")),
        "local_notion_settings_path": Path(
            os.environ.get("LOCAL_NOTION_SETTINGS_PATH", CURRENT_DIR / "../../token/notion_setting.json")
        ),
        "local_client_secret_path": Path(
            os.environ.get("LOCAL_CLIENT_SECRET_PATH", CURRENT_DIR / "../../token/client_secret.json")
        ),
        "local_credentials_path": Path(
            os.environ.get("LOCAL_CREDENTIALS_PATH", CURRENT_DIR / "../../token/token.pkl")
        ),
    }

if __name__ == "__main__":
    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold green]🔧 Configuration Source")
    pprint(generate_config("test-uuid"), max_depth=3)
