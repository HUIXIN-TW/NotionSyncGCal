import json
from datetime import timedelta, date

_REQUIRED_LOCAL_KEYS = frozenset(
    {
        "database_id",
        "goback_days",
        "goforward_days",
        "timecode",
        "timezone",
        "default_event_length",
        "default_start_time",
        "gcal_dic",
        "page_property",
    }
)


class SettingError(Exception):
    """Custom exception to handle setting errors in the Notion class."""

    def __init__(self, message):
        super().__init__(message)


class NotionConfig:
    """Handles Notion configuration management."""

    def __init__(self, config, logger):
        self.config = config
        self.logger = logger
        self.mode = config.get("mode")
        self.setting = self.format_settings(self.load_settings())

    def load_settings(self):
        config = self.config
        if not config:
            raise SettingError("Configuration is required to load settings.")
        if self.mode == "cloud":
            try:
                from utils.dynamodb_utils import get_notion_config_by_uuid

                response = get_notion_config_by_uuid(config.get("uuid"))
                self.logger.debug(f"Loading Notion Configuration from DynamoDB: type={type(response).__name__}")
                return response
            except Exception as e:
                raise SettingError(f"Error loading Notion config from DynamoDB: {e}") from e
        if self.mode == "local":
            path = config.get("notion_setting_path")
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except FileNotFoundError:
                raise SettingError(f"Local Notion config file not found: {path}")
            except json.JSONDecodeError as e:
                raise SettingError(f"Local Notion config file is not valid JSON: {e}")
            except Exception as e:
                raise SettingError(f"Error reading local Notion config: {e}") from e
            missing = _REQUIRED_LOCAL_KEYS - set(data.keys())
            if missing:
                raise SettingError(f"Local Notion config is missing required keys: {sorted(missing)}")
            return data
        raise SettingError(f"Unknown config mode '{self.mode}'. Expected 'cloud' or 'local'.")

    def format_settings(self, setting):
        """Applies settings from the data dictionary to attributes of the Notion class."""
        try:
            self.logger.debug(f"Formatting Notion settings: type={type(setting).__name__}")
            # Date range settings
            setting["after_date"] = (date.today() + timedelta(days=-int(setting["goback_days"]))).strftime("%Y-%m-%d")
            setting["before_date"] = (date.today() + timedelta(days=int(setting["goforward_days"]))).strftime(
                "%Y-%m-%d"
            )
            setting.setdefault("notion_api_version", "2022-06-28")
            setting.setdefault("data_source_id", None)

            # ISO format for Google Calendar API
            setting["google_timemin"] = (date.today() + timedelta(days=-int(setting["goback_days"]))).strftime(
                f"%Y-%m-%dT%H:%M:%S{setting['timecode']}"
            )
            setting["google_timemax"] = (date.today() + timedelta(days=int(setting["goforward_days"]))).strftime(
                f"%Y-%m-%dT%H:%M:%S{setting['timecode']}"
            )

            # Clean Page properties
            setting["page_property"] = setting["page_property"][0]

            # Google calendar settings
            gcal_name_dict = setting["gcal_dic"][0]  # read it once from input
            self.logger.debug(f"gcal_dic[0] type={type(gcal_name_dict).__name__}")
            setting["gcal_name_dict"] = gcal_name_dict  # store with clear name
            setting["gcal_id_dict"] = self.convert_key_to_value(gcal_name_dict)  # updated variable name
            setting["gcal_default_name"] = list(gcal_name_dict)[0]  # updated variable name
            setting["gcal_default_id"] = list(setting["gcal_id_dict"])[0]
            del setting["gcal_dic"]
            return setting
        except KeyError as e:
            self.logger.error(f"Failed to apply setting: {e}")
            raise SettingError(f"Failed to apply setting: {e}")

    def convert_key_to_value(self, gcal_name_dict):
        return {value: key for key, value in gcal_name_dict.items()}

    def get_cal_name(self, cal_id):
        return self.user_setting["gcal_id_dict"].get(cal_id)

    def get_cal_id(self, cal_name):
        return self.user_setting["gcal_name_dict"].get(cal_name)

    def get(self):
        return self.setting


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

    # APP_MODE must be set in the shell (e.g. APP_MODE=local or APP_MODE=cloud)
    config = generate_config()
    notion = NotionConfig(config, logger)

    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold green]🔧 Notion Config Script")
    console.print("[green]📋 Full Notion Property:[/]")
    pprint(notion.setting)
