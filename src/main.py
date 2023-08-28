import os
import sys
import json
import time
from datetime import datetime

def import_sync_module():
    try:
        import Sync as s
        return s
    except ImportError:
        print("Error: Unable to import the Sync module.")
        sys.exit()

def get_cmd_args():
    try:
        return sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    except IndexError:
        return None, 1, 1

def main():
    # Get the command line arguments
    cmd, goback_value, goforward_days = get_cmd_args()

    # If users want to modify the JSON file
    if cmd == "-m":
        print(f"Going to set goback_days = {goback_value}")
        print(f"Going to set goforward_days = {goforward_days}")

        show_action = input("Do you want to modify json file (notion_setting.json) ? Y/N:  ")
        if show_action.lower() in ["y", "yes"]:
            modify_json(goback_value, goforward_days)
        else:
            print("Not modifying the JSON file...")
            sys.exit()

    # If users want to print on terminal or redirect to file
    show_action = input("Do you want to redirect to file? Y/N:  ")
    print("\n")

    # Import the Sync module
    s = import_sync_module()

    # If users want to redirect to file
    if show_action.lower() in ["y", "yes"]:
        write_to_file()
    # If users want to print on terminal
    else:
        print("Displaying output on the terminal...")
        run_sync_notion_gcal(s, sys.argv)


def write_to_file():
    try:
        temp = sys.stdout  # Store the default stdout
        cmd_name = " ".join(sys.argv)
        today = datetime.today().strftime("%Y-%m-%dT%H:%M:%S")
        filename = f"show_results_{today}.txt"
        with open(filename, "w") as f:
            sys.stdout = f  # Redirect output to the file
            print("----------------------------------------------------")
            print(f"File Name: {cmd_name}")
            print(f"Date Time: {today}")
            print("----------------------------------------------------")
            print()
            run_sync_notion_gcal(sys.argv)  # Call the synchronization function
        sys.stdout = temp  # Restore the default stdout
        print(f"Completed! The output has been saved to {filename}.")
    except Exception as e:
        print("An error occurred while redirecting output to a file:")
        print(e)
    finally:
        sys.stdout = temp  # Restore the default stdout


def run_sync_notion_gcal(s, cmd):
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

#TODO: Effectively modify the JSON file
def modify_json(goback_value=1, goforward_days=1):
    # Get the absolute path to the current directory
    current_dir = os.path.dirname(os.path.abspath(__file__))
    FILEPATH = os.path.join(current_dir, "../token/notion_setting.json")
    
    # Read the current contents of the JSON file
    with open(FILEPATH, 'r') as file:
        data = json.load(file)
    
    # Modify the "goback_days" value
    data["goback_days"] = goback_value
    data["goforward_days"] = goforward_days
    print("Setting goback_days =", goback_value)
    print("Setting goforward_days =", goforward_days)
    
    # Write the modified data back to the JSON file
    with open(FILEPATH, 'w') as file:
        json.dump(data, file, indent=2)

    # Print the current contents of the JSON file
    with open(FILEPATH, 'r') as file:
        data = json.load(file)
        formatted_data = json.dumps(data, indent=2)
        for line in formatted_data.split('\n'):
            print(line)
    print("Modified the goback_days and goforward_days values in notion_setting.json")
    print("\n")


if __name__ == "__main__":
    s = None
    main()
