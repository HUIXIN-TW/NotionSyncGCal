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
        self.token = self.load_settings(config.get("uuid") if self.mode == "serverless" else None)

    def load_settings(self, uuid=None):
        config = self.config
        if not config:
            raise SettingError("Configuration is required to load settings.")
        try:
            if self.mode == "serverless":
                ddb_client = boto3.client("dynamodb")
                response = ddb_client.get_item(
                    TableName=config.get("dynamo_notion_token_table"),
                    Key={"uuid": {"S": uuid}},
                )
                data = response.get("Item")
                self.logger.debug(f"Loading settings from DynamoDB: {config.get('dynamo_notion_token_table')}")
                return data.get("accessToken").get("S")
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

    # python -m src.notion.notion_token
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
