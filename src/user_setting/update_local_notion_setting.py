import json
from pathlib import Path

# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent.resolve()

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = (CURRENT_DIR / "../../token/notion_setting.json").resolve()


def update_date_range(goback_value, goforward_days):
    """Modify the goback_days and goforward_days in notion_setting.json"""
    data = read_json()
    data["goback_days"], data["goforward_days"] = goback_value, goforward_days
    print(f"Modified goback_days to {goback_value} and goforward_days to {goforward_days} in notion_setting.json")
    write_json(data)


def update_page_property(page_property, page_property_value):
    """Modify the page_property in notion_setting.json"""
    data = read_json()
    data["page_property"][0][page_property] = page_property_value
    print(f"Modified page_property: {page_property} as {page_property_value} in notion_setting.json")
    write_json(data)


def update_notion_token(notion_token):
    """Modify the notion_token in notion_setting.json"""
    data = read_json()
    data["notion_token"] = notion_token
    print(f"Modified notion_token to {notion_token} in notion_setting.json")
    write_json(data)


def update_database_id(database_id):
    """Modify the notion_database_id in notion_setting.json"""
    data = read_json()
    data["database_id"] = database_id
    print(f"Modified database_id to {database_id} in notion_setting.json")
    write_json(data)


def read_json():
    with open(NOTION_SETTINGS_PATH, "r") as file:
        data = json.load(file)
    return data


def write_json(data):
    with open(NOTION_SETTINGS_PATH, "w") as file:
        json.dump(data, file, indent=4)


if __name__ == "__main__":
    # update_date_range(0,1)
    # update_page_property("Task_Notion_Name", "YOUR NEW TASK NAME HERE")
    print("You can update the notion_setting.json file by calling the functions in update_notion_setting.py")
