import os
import sys
import json
import time
from datetime import datetime

NOTION_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../token/notion_setting.json")

def import_sync_module():
    try:
        import Sync as s
        return s
    except ImportError:
        print("Error: Unable to import the Sync module.")
        sys.exit()

def ask_yes_no(question):
    """Ask a yes or no question and return True if the answer is 'yes'."""
    answer = input(question).strip().lower()
    return answer in ["y", "yes"]

def modify_json(cmd):
    """Modify the goback_days and goforward_days in notion_setting.json"""
    goback_value, goforward_days = int(cmd[3]), int(cmd[4])

    with open(NOTION_SETTINGS_PATH, 'r') as file:
        data = json.load(file)
        print(json.dumps(data, indent=2))

    data["goback_days"], data["goforward_days"] = goback_value, goforward_days
    
    print("\n")
    print(f"Modified goback_days to {goback_value} and goforward_days to {goforward_days} in notion_setting.json")
    print("\n")

    with open(NOTION_SETTINGS_PATH, 'w') as file:
        json.dump(data, file, indent=2)
        print(json.dumps(data, indent=2))

def execute_sync_action(s, cmd):
    #TODO: add a function to check the cmd is valid or not
    start_time = time.time()  # start time
    # default: update from notion to google
    if len(cmd) == 1 or cmd[1] == "-nm" or cmd[1] == "--update-modified-on-notion":
        s.notion_to_gcal(action=0, updateEverything=True)
    # default: update from notion to google, including NeedGCalUpdate is false
    elif cmd[1] == "-na" or cmd[1] == "--update-all-on-notion":
        s.notion_to_gcal(action=0, updateEverything=False)
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
    # TODO: can extract the notion page id from the url
    elif cmd[1] == "-np" or cmd[1] == "--notion-page":
        s.notion_to_gcal(action=1, updateEverything=True)
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
    print("\n")
    print("----------------------------- TimeInformation -----------------------------")
    print(f"Command Line: {' '.join(cmd)}")
    print("Current Time =", current_time)
    print("Process finished in %.2f seconds" % (end_time - start_time))
    print("-------------------------------- COMPLETED --------------------------------")
    print("###########################################################################")
    print("################################### END ###################################")
    print("\n")


def write_to_file(cmd):
    backup_stdout = sys.stdout

    today = datetime.today().strftime("%Y-%m-%dT%H:%M:%S")
    filename = f"show_results_{today}.txt"

    try:
        with open(filename, "w") as f:
            sys.stdout = f
            print_results_header(cmd)
            execute_sync_action(s, cmd)
        print(f"Completed! The output has been saved to {filename}.")
    except Exception as e:
        print(f"Error while writing to {filename}: {e}")
    finally:
        sys.stdout = backup_stdout

def print_results_header(cmd):
    print("----------------------------------------------------")
    print(f"Command: {' '.join(cmd)}")
    print(f"Date Time: {datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}")
    print("----------------------------------------------------")
    print()

def main():
    # check if the user want to modify json file
    try:
        if sys.argv[2] == "-m":
            modify_json(sys.argv)
    except:
        print("No json file is modified")
        pass

    # check if the user want to sync with new json file
    # if not yes, then exit the program
    if not ask_yes_no(f"Do you want to sync with new json file? Y/N: "):
        sys.exit()

    # check if the user want to redirect to file    
    redirect_to_file = ask_yes_no("Do you want to redirect to file? Y/N: ")

    s = import_sync_module()

    if redirect_to_file:
        write_to_file(sys.argv)
    else:
        print("Displaying output on the terminal...")
        execute_sync_action(s, sys.argv)

if __name__ == "__main__":
    main()
