import os
import sys
import json
import time
from datetime import datetime, timedelta, date
from pathlib import Path

# Get the absolute path to the current directory
CURRENT_DIR = Path(__file__).parent

# Construct the absolute file paths within the container
NOTION_SETTINGS_PATH = CURRENT_DIR / "../token/notion_setting.json"


def import_sync_module():
    try:
        import sync as s

        return s
    except ImportError as e:
        raise ImportError(f"Critical dependency not found: {e}")


def ask_yes_no(question):
    """Ask a yes or no question and return True if the answer is 'yes'."""
    answer = input(question).strip().lower()
    return answer in ["y", "yes"]


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

def execute_sync_action(s, cmd, data):
    # TODO: Change 0, 1 ,2 into more meaningful name
    start_time = time.time()  # start time
    # default: update from notion to google
    if len(cmd) == 1 or cmd[1] == "-nm" or cmd[1] == "--update-modified-on-notion":
        notion_to_gcal = s.NotionToGCal(action=0, updateEverything=True)
        notion_to_gcal.main()
    # default: update from notion to google, including NeedGCalUpdate is false
    elif cmd[1] == "-na" or cmd[1] == "--update-all-on-notion":
        notion_to_gcal = s.NotionToGCal(action=0, updateEverything=False)
        notion_to_gcal.main()
    # update from google time and create new events
    elif cmd[1] == "-gt" or cmd[1] == "--google-time":
        s.gcal_to_notion(action=0)
    # create from google event only not update time format
    elif cmd[1] == "-gc" or cmd[1] == "--google-create":
        s.gcal_to_notion(action=1)
    # update from google to notion, danger zone from google description to notion description
    elif cmd[1] == "-ga" or cmd[1] == "--google-all":
        check_again = input(
            "Do you want to overwrite Notion? This action cannot be undone! Enter [YES, OVERWRITE]: "
        )
        if check_again == "YES, OVERWRITE":
            s.gcal_to_notion(action=2)
    # delete google cal via notion Done?
    elif cmd[1] == "-r" or cmd[1] == "--remove":
        s.deleteEvent()
    # print sample
    elif cmd[1] == "-s" or cmd[1] == "--sample":
        try:
            n = int(cmd[2])
        except IndexError:
            n = 1
        try:
            name = cmd[3]
        except IndexError:
            name = "Task"
        print("\nNotion Events:")
        s.notion_event_sample(num=n)
        print("\nGoogle Events:")
        s.gcal_event_sample(name=name, num=n)
    else:
        print("Error: Invalid command")

    end_time = time.time()  # end time
    current_time = datetime.now().strftime("%H:%M:%S")
    after_date = (date.today() + timedelta(days=data["goback_days"])).strftime(
        "%Y-%m-%d"
    )
    before_date = (date.today() + timedelta(days=data["goforward_days"])).strftime(
        "%Y-%m-%d"
    )
    print("\n")
    print("----------------------------- TimeInformation -----------------------------")
    print(f"Command Line: {' '.join(cmd)}")
    print(f"After Date {after_date} Included, Before Date {before_date} Not Included")
    print("Current Time =", current_time)
    print("Process finished in %.2f seconds" % (end_time - start_time))
    print("-------------------------------- COMPLETED --------------------------------")
    print("###########################################################################")
    print("################################### END ###################################")
    print("\n")


def main():
    # check if the user want to modify json file
    data = read_json()
    try:
        if sys.argv[2] == "-m":
            modify_json(sys.argv, data)
    except:
        print("No json file is modified")

    s = import_sync_module()

    print("Displaying output on the terminal...")
    execute_sync_action(s, sys.argv, data)


if __name__ == "__main__":
    main()
