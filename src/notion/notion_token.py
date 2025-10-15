import json
import boto3


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class NotionToken:
    """Handles Notion API token"""

    def __init__(self, config, logger):
        self.logger = logger
        self.config = config
        self.mode = config.get("mode")
        self.token = self.load_settings(config.get("uuid") if self.mode == "s3" else None)

    def load_settings(self, uuid=None):
        config = self.config
        if not config:
            raise SettingError("Configuration is required to load settings.")
        try:
            if self.mode == "s3":
                s3 = boto3.client("s3")
                response = s3.get_object(Bucket=config.get("s3_bucket_name"), Key=config.get("s3_key_notion_token"))
                self.logger.debug(
                    f"Loading settings from S3: {config.get('s3_bucket_name')}/{config.get('s3_key_notion_token')}"
                )
                response = json.loads(response["Body"].read().decode("utf-8"))
                return response.get("access_token")
            elif self.mode == "local":
                self.logger.info(f"Loading settings from local file: {config.get('local_notion_settings_path')}")
                with open(config.get("local_notion_settings_path"), encoding="utf-8") as f:
                    response = json.load(f)
                return response.get("notion_token")
        except Exception as e:
            raise SettingError(f"Error loading local settings file: {e}")

    def get(self):
        return self.token


if __name__ == "__main__":
    import sys
    import logging
    from pathlib import Path

    # python -m src.notion.notion_config
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    # Add the src directory to the Python path
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from config.config import generate_config  # noqa: E402

    config = generate_config("")
    notion = NotionToken(config, logger)

    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold green]🔧 Notion Access Token")
    pprint(notion.get())
