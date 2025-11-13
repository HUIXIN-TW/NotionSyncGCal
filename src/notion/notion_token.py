import json
from utils.dynamodb_utils import get_notion_token_by_uuid  # noqa: E402


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
        self.uuid = config.get("uuid")
        self.token = self.load_settings(self.uuid if self.mode == "serverless" else None)

    def load_settings(self, uuid=None):
        config = self.config
        if not config:
            raise SettingError("Configuration is required to load settings.")
        try:
            if self.mode == "serverless":
                response = get_notion_token_by_uuid(uuid)
                return response.get("accessToken")
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
