import json
import boto3
from datetime import timedelta, date


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
        """Loads settings from either S3 or a local JSON file based on the config."""
        config = self.config
        if not config:
            raise SettingError("Configuration is required to load settings.")
        try:
            if self.mode == 's3':
                s3 = boto3.client("s3")
                response = s3.get_object(Bucket=config.get("s3_bucket_name"), Key=config.get("s3_key_notion_config"))
                self.logger.debug(
                    f"Loading settings from S3: {config.get('s3_bucket_name')}/{config.get('s3_key_notion_config')}"
                )
                return json.loads(response["Body"].read().decode("utf-8"))

            elif self.mode == 'local':
                self.logger.info(f"Loading settings from local file: {config.get('local_notion_settings_path')}")
                with open(config.get("local_notion_settings_path"), encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            raise SettingError(f"Error loading local settings file: {e}")

    def format_settings(self, setting):
        """Applies settings from the data dictionary to attributes of the Notion class."""
        try:
            # Date range settings
            setting["after_date"] = (date.today() + timedelta(days=-setting["goback_days"])).strftime("%Y-%m-%d")
            setting["before_date"] = (date.today() + timedelta(days=setting["goforward_days"])).strftime("%Y-%m-%d")

            # ISO format for Google Calendar API
            setting["google_timemin"] = (date.today() + timedelta(days=-setting["goback_days"])).strftime(
                f"%Y-%m-%dT%H:%M:%S{setting['timecode']}"
            )
            setting["google_timemax"] = (date.today() + timedelta(days=setting["goforward_days"])).strftime(
                f"%Y-%m-%dT%H:%M:%S{setting['timecode']}"
            )

            # Clean Page properties
            setting["page_property"] = setting["page_property"][0]

            # Google calendar settings
            gcal_name_dict = setting["gcal_dic"][0]  # read it once from input
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

    @property
    def user_setting(self):
        setting = self.setting.copy()
        setting.pop("notion_token", None)
        return setting


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
    notion = NotionConfig(config, logger)

    from rich.console import Console
    from rich.pretty import pprint

    console = Console()
    console.rule("[bold green]🔧 Notion Config Script")
    console.print("[green]📋 Full Notion Property:[/]")
    pprint(notion.user_setting)
