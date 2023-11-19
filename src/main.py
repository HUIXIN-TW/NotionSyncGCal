import os
import sys
import json
import time
import logging
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
    """Execute synchronization action based on command line arguments."""
    start_time = time.perf_counter()

    try:  # start time
        # default: update from notion to google
        if len(cmd) == 1 or cmd[1] == "-nm" or cmd[1] == "--update-modified-on-notion":
            notion_to_gcal = s.NotionToGCal(action="UPDATE", updateEverything=True)
            notion_to_gcal.main()
        # default: update from notion to google, including NeedGCalUpdate is false
        elif cmd[1] == "-na" or cmd[1] == "--update-all-on-notion":
            notion_to_gcal = s.NotionToGCal(action="UPDATE", updateEverything=False)
            notion_to_gcal.main()
        # update from google time and create new events
        elif cmd[1] == "-gt" or cmd[1] == "--google-time":
            s.GCalToNotion(action="UPDATE_TIME_CREATE_NEW_BY_GOOGLE")
        # create from google event only not update time format
        elif cmd[1] == "-gc" or cmd[1] == "--google-create":
            s.GCalToNotion(action="UPDATE_TIME_BY_GOOGLE")
        # update from google to notion, danger zone from google description to notion description
        elif cmd[1] == "-ga" or cmd[1] == "--google-all":
            check_again = input(
                "Do you want to overwrite Notion? This action cannot be undone! Enter [YES, OVERWRITE]: "
            )
            if check_again == "YES, OVERWRITE":
                s.GCalToNotion(action="OVERWRITE_BY_GOOGLE")
        # delete google cal via notion Done?
        elif cmd[1] == "-r" or cmd[1] == "--remove": #bug
            s.deleteEvent()
        # print sample
        elif cmd[1] == "-s" or cmd[1] == "--sample": #bug
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
    except Exception as e:
        logging.error(f"Error executing action: {e}")

    end_time = time.perf_counter()
    log_time_information(cmd, start_time, end_time, data)
    logging.info("Process completed.")


def log_time_information(cmd, start_time, end_time, data):
    """Log time information for the executed action."""
    current_time = datetime.now().strftime("%H:%M:%S")
    after_date = (date.today() - timedelta(days=data["goback_days"])).strftime(
        "%Y-%m-%d"
    )
    before_date = (date.today() + timedelta(days=data["goforward_days"])).strftime(
        "%Y-%m-%d"
    )

    logging.info(f"Command Line: {' '.join(cmd)}")
    logging.info(f"After {after_date} Included, Before {before_date} Not Included")
    logging.info(f"Current Time = {current_time}")
    logging.info(f"Process finished in {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    data = read_json()
    try:
        if sys.argv[2] == "-m":
            modify_json(sys.argv, data)
    except:
        print("No json file is modified")

    sync_module = import_sync_module()

    print("Displaying output on the terminal...")
    execute_sync_action(sync_module, sys.argv, data)
