import os
from utils.token_crypto import (
    TokenCryptoError,
    decrypt_token,
    decrypt_token_if_encrypted,
)


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class NotionToken:
    """Loads a Notion token and fences cloud execution to one provider binding."""

    def __init__(self, config, logger):
        self.logger = logger
        self.config = config
        self.mode = config.get("mode")
        self.uuid = config.get("uuid")
        self._loaded_updated_at = None
        self._loaded_workspace_id = None
        self.token = self.load_settings(self.uuid if self.mode == "cloud" else None)

    def load_settings(self, uuid=None):
        if not self.config:
            raise SettingError("Configuration is required to load settings.")
        if self.mode == "cloud":
            try:
                from utils.dynamodb_utils import get_notion_token_by_uuid

                response = get_notion_token_by_uuid(uuid, consistent_read=True)
                self._loaded_updated_at = self._require_binding_value(
                    response.get("updatedAt"),
                    "Notion OAuth token updatedAt",
                )
                self._loaded_workspace_id = self._require_binding_value(
                    response.get("workspaceId"),
                    "Notion OAuth workspaceId",
                )
                try:
                    return decrypt_token(response.get("accessToken"))
                except TokenCryptoError as e:
                    raise SettingError(f"Failed to decrypt Notion token: {e}") from e
            except SettingError:
                raise
            except Exception as e:
                raise SettingError(f"Error loading Notion token from DynamoDB: {e}") from e
        if self.mode == "local":
            token = os.environ.get("NOTION_TOKEN", "").strip()
            if not token:
                raise SettingError("NOTION_TOKEN environment variable is required in local mode but is not set.")
            try:
                return decrypt_token_if_encrypted(token)
            except TokenCryptoError as e:
                raise SettingError(f"Failed to decrypt Notion token: {e}") from e
        raise SettingError(f"Unknown config mode '{self.mode}'. Expected 'cloud' or 'local'.")

    @staticmethod
    def _require_binding_value(value, label):
        if value is None:
            raise SettingError(f"{label} is missing.")
        normalized = str(value).strip()
        if not normalized:
            raise SettingError(f"{label} is missing.")
        return normalized

    def assert_admission_binding(self, admission_started_at_ms):
        """Reject a Notion OAuth row changed after backend admission began."""
        if self.mode != "cloud":
            return
        if isinstance(admission_started_at_ms, bool) or not isinstance(
            admission_started_at_ms, int
        ):
            raise SettingError("Sync admission timestamp is invalid.")
        try:
            loaded_updated_at_ms = int(self._loaded_updated_at)
        except (TypeError, ValueError) as exc:
            raise SettingError("Notion OAuth token updatedAt is invalid.") from exc
        if loaded_updated_at_ms > admission_started_at_ms:
            raise SettingError(
                "Notion OAuth connection changed after the sync job was admitted."
            )

    def assert_current_binding(self):
        """Fail closed if the persisted Notion OAuth binding changed during this job."""
        if self.mode != "cloud":
            return

        from utils.dynamodb_utils import get_notion_token_by_uuid

        try:
            current = get_notion_token_by_uuid(self.uuid, consistent_read=True)
        except ValueError as exc:
            raise SettingError(
                "Notion OAuth connection disappeared while the sync job was running."
            ) from exc

        current_updated_at = self._require_binding_value(
            current.get("updatedAt"),
            "Notion OAuth token updatedAt",
        )
        current_workspace_id = self._require_binding_value(
            current.get("workspaceId"),
            "Notion OAuth workspaceId",
        )
        if (
            current_updated_at != self._loaded_updated_at
            or current_workspace_id != self._loaded_workspace_id
        ):
            raise SettingError(
                "Notion OAuth connection changed while the sync job was running."
            )

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
