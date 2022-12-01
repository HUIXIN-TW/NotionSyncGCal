import os
import pickle
import json
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


# notion API setting 
class Notion:
    def __init__(self):
        fileName = "token/notion_setting.json"
        with open(fileName) as f:
            data = json.load(f)
        self.notion_token = data["notion_token"]
        self.database_id = data["database_id"]
        self.urlroot = data["urlroot"]
        self.timecode = data["timecode"]
        self.timezone = data["timezone"]
        self.goback_days = data["goback_days"]
        self.goforward_days = data["goforward_days"]
        self.delete_option = data["delete_option"]
        self.event_length = data["event_length"]
        self.start_time = data["start_time"]
        self.allday_option = data["allday_option"]
        self.gcal_default_name = data["gcal_default_name"]
        self.gcal_default_id = data["gcal_default_id"]
        self.gcal_dic = data["gcal_dic"][0]
        self.gcal_dic_key_to_value = data["gcal_dic_key_to_value"][0]
        self.page_property = data["page_property"][0]
    def gcal_dic_key_to_value(gcal_dic): #bug: cant call by init
        x = {}
        for key in gcal_dic[0]:
            x[gcal_dic[0][key]] = key
        return x
        

# google API setting
class Google:
    def __init__(self):
        pass

    # DO NOT SHARE WITH OTHERS
    def ask_creds(cls):
        # If modifying these scopes, delete the file `token.json`
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = None
        # The file token.pkl stores the user"s access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists("token/token.pkl"):
            try:
                creds = Credentials.from_authorized_user_file("token/token.pkl", scopes)
            except:
                os.remove("token/token.pkl")
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
            with open("token/token.pkl", "wb") as token:
                pickle.dump(creds, token)
                # Or use json
                # token.write(creds.to_json())

