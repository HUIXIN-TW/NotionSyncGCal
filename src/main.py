import sys
import time
from datetime import datetime

import Sync as s


# Limitation:
#   - Event Name: Only Notion to google will be a better version because it shows the CompleteIcon as prefix
#   - Event Description: Only Notion to google will be a better vesion because it shows the Initiative and Status


def main():
    show_action = input("Do you want to redirect to file? Y/N:  ")
    print("\n")

    if show_action not in ["Y", "y", "Yes", "yes", "YES"]:
        print("Show on the terminal...")
        sync_notion_gcal(sys.argv)
    else:
        try:
            temp = sys.stdout  # default output is console

            cmd_name = ""
            for name in sys.argv:
                cmd_name = cmd_name + " " + name

            today = datetime.today().strftime(f"%Y-%m-%dT%H:%M:%S")
            out_filename = f"show_results_{today}.txt"

            with open(out_filename, "w") as f:
                sys.stdout = f  # print into txt file
                print(
                    "--------------------------------------------------------------------------"
                )
                print(f"File Name:           {cmd_name}")
                print(f"Date Time:            {today}")
                print(
                    "--------------------------------------------------------------------------"
                )
                print("\n")
                sync_notion_gcal(sys.argv)
            sys.stdout = temp  # redirect to default std
            print(f"COMPLETED, please see {out_filename}")
        except:
            print("Error...")
            sys.exit(1)

    if show_action == ["both", "BOTH", "Both"]:
        print(f.readlines())


def sync_notion_gcal(cmd):
    start_time = time.time()  # Start time
    notion_action = 0  # default: notion to google update time section
    google_action = 0  # default: google to notion update time section

    if len(cmd) == 1:
        # default: update from notion to google
        s.notion_to_gcal(notion_action, True)
    elif cmd[1] == "-na" or cmd[1] == "--UPDATE-ALL-ON-NOTION":
        # default: update from notion to google
        # including NeedGCalUpdate is false
        s.notion_to_gcal(notion_action, False)
    elif cmd[1] == "-gt" or cmd[1] == "--GOOGLETIME":
        # update from google time and create new events
        s.gcal_to_notion(google_action)
    elif cmd[1] == "-gc" or cmd[1] == "--GOOGLECREATE":
        # create from google event only not update time format
        google_action = 1
        s.gcal_to_notion(google_action)
    elif cmd[1] == "-ga" or cmd[1] == "--GOOGLEALL":
        check_again = input(
            "Do you want to overwrite to Notion? It can't be undo! Enter [YES, OVERWRITE]:  "
        )
        if check_again == "YES, OVERWRITE":
            # update from google to notion
            # danger zone from google description to notion description
            google_action = 2
            s.gcal_to_notion(google_action)
    elif cmd[1] == "-np" or cmd[1] == "NOTIONPAGE":  # still bug
        notion_action = 1
        s.notion_to_gcal(notion_action, True)
    elif cmd[1] == "-r" or cmd[1] == "--REMOVE":
        # delete google cal via notion Done?
        s.deleteEvent()
    elif cmd[1] == "-s" or cmd[1] == "--SAMPLE":
        # print sample
        try:
            n = int(cmd[2])
        except:
            n = 1
        try:
            name = [3]
        except:
            name = "Task"
        print("\n")
        print(
            "-------------------------------- Notion ----------------------------------"
        )
        s.notion_event_sample(n)
        print("\n")
        print(
            "--------------------------------  GCal  ----------------------------------"
        )
        s.gcal_event_sample(name, n)
    else:
        print("Error: No command")

    end_time = time.time()  # end time
    current_time = datetime.now().strftime("%H:%M:%S")
    print("\n")
    print("----------------------------- TimeInformation -----------------------------")
    print(f"Command Line: {cmd}")
    print("Current Time =", current_time)
    print("Process finished --- %s seconds ---" % (end_time - start_time))
    print("-------------------------------- COMPLETED --------------------------------")
    print("###########################################################################")
    print("################################### END ###################################")
    print("\n")
    print("\n")


if __name__ == "__main__":
    main()
