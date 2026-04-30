import os
from utils.token_crypto import TokenCryptoError, decrypt_token_if_encrypted


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
        self.token = self.load_settings(self.uuid if self.mode == "cloud" else None)

    def load_settings(self, uuid=None):
        if not self.config:
            raise SettingError("Configuration is required to load settings.")
        if self.mode == "cloud":
            try:
                from utils.dynamodb_utils import get_notion_token_by_uuid
                response = get_notion_token_by_uuid(uuid)
                try:
                    return decrypt_token_if_encrypted(response.get("accessToken"))
                except TokenCryptoError as e:
                    raise SettingError(f"Failed to decrypt Notion token: {e}") from e
            except SettingError:
                raise
            except Exception as e:
                raise SettingError(f"Error loading Notion token from DynamoDB: {e}") from e
        if self.mode == "local":
            token = os.environ.get("NOTION_TOKEN", "").strip()
            if not token:
                raise SettingError(
                    "NOTION_TOKEN environment variable is required in local mode but is not set."
                )
            try:
                return decrypt_token_if_encrypted(token)
            except TokenCryptoError as e:
                raise SettingError(f"Failed to decrypt Notion token: {e}") from e
        raise SettingError(f"Unknown config mode '{self.mode}'. Expected 'cloud' or 'local'.")

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

    # APP_MODE must be set in the shell (e.g. APP_MODE=local or APP_MODE=cloud)
    config = generate_config()
    notion = NotionToken(config, logger)

    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold green]🔧 Notion Access Token")
    pprint(notion.get())
