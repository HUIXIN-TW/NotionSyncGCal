import os
import json
import pickle
from notion_client import Client
from datetime import timedelta, date
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


FILEPATH = "token/notion_setting.json"
CREDPATH = "token/token.pkl"


class Notion():
    def __init__(self):
        if os.path.exists(FILEPATH):
            with open(FILEPATH) as f:
                data = json.load(f)
        else:
            print("Make sure you store notion_setting.json in toke folder")
        self.DATABASE_ID = data["database_id"]
        # open up a task and then copy the URL root up to the "p="
        self.URLROOT = data["urlroot"]
        # Change timecode to be representative of your timezone, it has to be adjusted as daylight savings
        self.TIMECODE = data["timecode"]
        self.TIMEZONE = data["timezone"]
        # Notion search range: go back to which date?
        # google search range: go back to which date?
        self.AFTER_DATE = (date.today() + timedelta(days=-
                           data["goback_days"])).strftime(f"%Y-%m-%d")
        self.BEFORE_DATE = (
            date.today() + timedelta(days=+ data["goforward_days"])).strftime(f"%Y-%m-%d")
        self.GOOGLE_TIMEMIN = (date.today(
        ) + timedelta(days=- data["goback_days"])).strftime(f"%Y-%m-%dT%H:%M:%S{self.TIMECODE}")
        self.GOOGLE_TIMEMAX = (date.today(
        ) + timedelta(days=+ data["goforward_days"])).strftime(f"%Y-%m-%dT%H:%M:%S{self.TIMECODE}")
        self.DELETE_OPTION = data["delete_option"]
        self.DEFAULT_EVENT_LENGTH = data["default_event_length"]
        # 8 would be 8 am. 16 would be 4 pm. Only int
        self.DEFAULT_EVENT_START = data["default_start_time"]
        # 0 Notion -> GCal: be created as an all-day event
        # 1 Notion -> GCal: be created at whatever hour you defined in the DEFAULT_EVENT_START
        self.ALLDAY_OPTION = data["allday_option"]
        self.GCAL_DEFAULT_NAME = data["gcal_default_name"]
        self.GCAL_DEFAULT_ID = data["gcal_default_id"]
        # MULTIPLE CALENDAR PART:
        self.GCAL_DIC = data["gcal_dic"][0]
        self.GCAL_DIC_KEY_TO_VALUE = self.gcal_dic_key_to_value(
            data["gcal_dic"][0])
        # DATABASE SPECIFIC EDITS
        self.TASK_NOTION_NAME = data["page_property"][0]["Task_Notion_Name"]
        self.DATE_NOTION_NAME = data["page_property"][0]["Date_Notion_Name"]
        self.INITIATIVE_NOTION_NAME = data["page_property"][0]["Initiative_Notion_Name"]
        self.EXTRAINFO_NOTION_NAME = data["page_property"][0]["ExtraInfo_Notion_Name"]
        self.LOCATION_NOTION_NAME = data["page_property"][0]["Location_Notion_Name"]
        self.ON_GCAL_NOTION_NAME = data["page_property"][0]["On_GCal_Notion_Name"]
        self.NEEDGCALUPDATE_NOTION_NAME = data["page_property"][0]["NeedGCalUpdate_Notion_Name"]
        self.GCALEVENTID_NOTION_NAME = data["page_property"][0]["GCalEventId_Notion_Name"]
        self.LASTUPDATEDTIME_NOTION_NAME = data["page_property"][0]["LastUpdatedTime_Notion_Name"]
        self.CALENDAR_NOTION_NAME = data["page_property"][0]["Calendar_Notion_Name"]
        self.CURRENT_CALENDAR_ID_NOTION_NAME = data["page_property"][0]["Current_Calendar_Id_Notion_Name"]

        # set at 0 if you want the delete column
        # set at 1 if you want nothing deleted
        self.DELETE_NOTION_NAME = data["page_property"][0]["Delete_Notion_Name"]
        self.STATUS_NOTION_NAME = data["page_property"][0]["Status_Notion_Name"]
        self.PAGE_ID_NOTION_NAME = data["page_property"][0]["Page_ID_Notion_Name"]
        self.COMPLETEICON_NOTION_NAME = data["page_property"][0]["CompleteIcon_Notion_Name"]
        self.SKIP_DESCRIPTION_CONDITION = data["skip_description_condition"]
        # set notion auth
        self.NOTION = Client(auth=data["notion_token"])
        print("--- Init Toke.py Notion class ---")

    def gcal_dic_key_to_value(self, gcal_dic):
        key_to_value = {}
        for key in gcal_dic:
            key_to_value[gcal_dic[key]] = key
        return key_to_value

# google API setting


class Google():
    def __init__(self):
        # If the token expires, the other python script GCalToken.py creates a new token for the program to use
        if os.path.exists(CREDPATH):
            credentials = pickle.load(open(CREDPATH, "rb"))
            self.service = build("calendar", "v3", credentials=credentials)
        else:
            print("Make sure you store token.pkl in toke folder")
        if os.path.exists(FILEPATH):
            with open(FILEPATH) as f:
                data = json.load(f)
        else:
            print("Make sure you store notion_setting.json in toke folder")
        try:
            calendar = self.service.calendars().get(
                calendarId=data["gcal_default_id"]).execute()
            print(f"--- Init Toke.py Google class ---")
            print(f"--- {self.service} ---")
        except:
            # ready to refresh the token and close the program
            print(
                "Checking if the Google Calendar API token expires. \nRun Token.py to update the token.pkl.")
            print(
                "Google Cloud Platform https://console.cloud.google.com/apis/credentials")
            self.ask_creds(CREDPATH)
            os._exit(1)

    # DO NOT SHARE WITH OTHERS

    def ask_creds(self, CREDPATH):
        # If modifying these scopes, delete the file `token.json`
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        # The file token.pkl stores the user"s access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(CREDPATH):
            try:
                creds = Credentials.from_authorized_user_file(
                    CREDPATH, scopes)
            except:
                os.remove(CREDPATH)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "token/client_secret.json", scopes)
                creds = flow.run_local_server(port=0)
                print("------------------Refresh tokens------------------")
                print("\n")
                # Or post the cred to terminal
                # creds = flow.run_console()
            # Save the credentials for the next run
            with open(CREDPATH, "wb") as token:
                pickle.dump(creds, token)
