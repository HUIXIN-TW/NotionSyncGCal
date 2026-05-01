import json
import os
from pathlib import Path

# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = CURRENT_DIR.parent.parent

# Local CLI mutations only touch the structured local config file.
NOTION_SETTINGS_PATH = (REPO_ROOT / "config" / "local.notion-setting.json").resolve()


class LocalSettingUpdateError(Exception):
    """Raised when local structured config cannot be updated safely."""


def _ensure_local_mode():
    app_mode = os.environ.get("APP_MODE")
    if app_mode and app_mode != "local":
        raise LocalSettingUpdateError("Local Notion config updates are only supported when APP_MODE=local.")


def update_date_range(goback_value, goforward_days):
    """Modify the goback_days and goforward_days in local.notion-setting.json."""
    data = read_json()
    data["goback_days"], data["goforward_days"] = goback_value, goforward_days
    print(
        f"Modified goback_days to {goback_value} and goforward_days to {goforward_days} "
        "in config/local.notion-setting.json"
    )
    write_json(data)


def update_page_property(page_property, page_property_value):
    """Modify the page_property in local.notion-setting.json."""
    data = read_json()
    data["page_property"][0][page_property] = page_property_value
    print(f"Modified page_property: {page_property} as {page_property_value} in config/local.notion-setting.json")
    write_json(data)


def update_notion_token(notion_token):
    """Do not write secrets into local structured config."""
    raise LocalSettingUpdateError("Notion tokens must be supplied via NOTION_TOKEN, not local config JSON.")


def update_database_id(database_id):
    """Modify the notion_database_id in local.notion-setting.json."""
    data = read_json()
    data["database_id"] = database_id
    print(f"Modified database_id to {database_id} in config/local.notion-setting.json")
    write_json(data)


def read_json():
    _ensure_local_mode()
    with open(NOTION_SETTINGS_PATH, "r") as file:
        data = json.load(file)
    return data


def write_json(data):
    _ensure_local_mode()
    with open(NOTION_SETTINGS_PATH, "w") as file:
        json.dump(data, file, indent=4)


if __name__ == "__main__":
    # update_date_range(0,1)
    # update_page_property("Task_Notion_Name", "YOUR NEW TASK NAME HERE")
    print("You can update the notion_setting.json file by calling the functions in update_notion_setting.py")
