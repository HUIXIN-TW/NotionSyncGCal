import sys
import json
from pathlib import Path

# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent.resolve()

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = (CURRENT_DIR / "../../token/notion_setting.json").resolve()


def modify_json(cmd, data):
    """Modify the goback_days and goforward_days in notion_setting.json"""
    goback_value, goforward_days = int(cmd[3]), int(cmd[4])
    data["goback_days"], data["goforward_days"] = goback_value, goforward_days
    print(
        f"Modified goback_days to {goback_value} and goforward_days to {goforward_days} in notion_setting.json"
    )
    with open(NOTION_SETTINGS_PATH, "w") as file:
        json.dump(data, file, indent=2)
        print("Updated notion_setting.json:")
        print(json.dumps(data, indent=2))


def read_json():
    with open(NOTION_SETTINGS_PATH, "r") as file:
        data = json.load(file)
        print("Current notion_setting.json:")
        print(json.dumps(data, indent=2))
    return data

def main():
    # check if the user want to modify json file
    data = read_json()
    try:
        if sys.argv[2] == "-m":
            modify_json(sys.argv, data)
    except:
        print("No json file is modified")