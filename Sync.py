from notion_client import Client
from googleapiclient.discovery import build

import os
import sys
import pickle
from datetime import datetime, timedelta, date

#import NotionToken as nt
#import GCalToken as gt
import Token


nt = Token.Notion()
gt = Token.Google()






##### The Set-Up Section - Notion #####
#get notion token
NOTION_TOKEN = nt.notion_token
#get notion database
database_id = nt.database_id
#open up a task and then copy the URL root up to the "p="
urlRoot = nt.urlroot
#Change timecode to be representative of your timezone, it has to be adjusted as daylight savings
timecode = nt.timecode
#Notion search range: go back to which date?
#google search range: go back to which date?
gobackdays = nt.goback_days
goforwarddays = nt.goforward_days
after_date = (date.today() + timedelta( days = - gobackdays)).strftime(f"%Y-%m-%d")
before_date = (date.today() + timedelta( days = + goforwarddays)).strftime(f"%Y-%m-%d")
google_timemin = (date.today() + timedelta( days = - gobackdays )).strftime(f"%Y-%m-%dT%H:%M:%S{timecode}")
google_timemax  = (date.today() + timedelta( days = + goforwarddays )).strftime(f"%Y-%m-%dT%H:%M:%S{timecode}")
#DATABASE SPECIFIC EDITS
Task_Notion_Name = nt.page_property["Task_Notion_Name"]
Date_Notion_Name = nt.page_property["Date_Notion_Name"]
Initiative_Notion_Name = nt.page_property["Initiative_Notion_Name"]
ExtraInfo_Notion_Name = nt.page_property["ExtraInfo_Notion_Name"]
Location_Notion_Name = nt.page_property["Location_Notion_Name"]
On_GCal_Notion_Name = nt.page_property["On_GCal_Notion_Name"]
NeedGCalUpdate_Notion_Name = nt.page_property["NeedGCalUpdate_Notion_Name"]
GCalEventId_Notion_Name = nt.page_property["GCalEventId_Notion_Name"]
LastUpdatedTime_Notion_Name  = nt.page_property["LastUpdatedTime_Notion_Name"]
Calendar_Notion_Name = nt.page_property["Calendar_Notion_Name"]
Current_Calendar_Id_Notion_Name = nt.page_property["Current_Calendar_Id_Notion_Name"]
Delete_Notion_Name = nt.page_property["Delete_Notion_Name"]
Status_Notion_Name = nt.page_property["Status_Notion_Name"]
Page_ID_Notion_Name = nt.page_property["Page_ID_Notion_Name"]
CompleteIcon_Notion_Name = nt.page_property["CompleteIcon_Notion_Name"]
#set at 0 if you want the delete column 
#set at 1 if you want nothing deleted
DELETE_OPTION = nt.delete_option




##### The Set-Up Section - GCal #####
#This is where you keep the pickle file that has the Google Calendar Credentials
credentialsLocation = "token/token.pkl"
#This is how many minutes the default event length is. Feel free to change it as you please
DEFAULT_EVENT_LENGTH = nt.event_length
#Choose your respective time zone: http://www.timezoneconverter.com/cgi-bin/zonehelp.tzc
timezone = nt.timezone
#8 would be 8 am. 16 would be 4 pm. Only int 
DEFAULT_EVENT_START = nt.start_time
#0 Notion -> GCal: be created as an all-day event
#1 Notion -> GCal: be created at whatever hour you defined in the DEFAULT_EVENT_START
AllDayEventOption = nt.allday_option
#MULTIPLE CALENDAR PART:
DEFAULT_CALENDAR_ID = nt.gcal_default_id
DEFAULT_CALENDAR_NAME = nt.gcal_default_name
calendarDictionary = nt.gcal_dic
calendarDictionary_trans = nt.gcal_dic_key_to_value




##### The API INTERFACE Section   #####
#This is where we set up the connection with the Notion API
os.environ["NOTION_TOKEN"] = NOTION_TOKEN
notion = Client(auth=os.environ["NOTION_TOKEN"])
#If the token expires, the other python script GCalToken.py creates a new token for the program to use
if os.path.exists("token/token.pkl"):
    credentials = pickle.load(open(credentialsLocation, "rb"))
    service = build("calendar", "v3", credentials=credentials)
try:
    calendar = service.calendars().get(calendarId=DEFAULT_CALENDAR_ID).execute()
except:
    #ready to refresh the token and close the program
    print("Check if the Google Calendar API token expires. \nRun GCalToken.py to update the token.pkl, then click the URL.")
    print("Go to check Google Cloud Platform https://console.cloud.google.com/apis/credentials")
    gt.ask_creds()
    os._exit(1)
print("\n")
print("\n")
print("################################## START ##################################")
print("###########################################################################")
print(f"--- Sync.py | After {after_date} Included, Before {before_date} Not Included ---")




#######################################
##### The Method Section - Google #####
#######################################
#METHOD TO FIND GCAL EVENT IDs
def all_gcal_eventid(which):
    #get all google events
    print("\n")
    print(f"{which} | Get all Google event")
    events = [] #contains all cals and their tasks
    for calid in calendarDictionary.values():
        x = queryGCalId(calid)
        events.extend(x["items"])
    return events

#METHOD TO MAKE GOOGLE TIME FORMAT TO NOTION
def DateTimeIntoNotionFormat(dateTimeValue):
    return dateTimeValue.strftime(f"%Y-%m-%dT%H:%M:%S{timecode}")

#METHOD TO MAKE A NOTION URL
def makeTaskURL(ending, urlRoot): #urlRoot: Notion Page Prefix, ending: Notion Page Suffix
    urlId = ending.replace("-", "")
    return urlRoot + urlId #Notion Page ID  

#METHOD TO MAKE A CALENDAR EVENT DESCRIPTION
def makeEventDescription(initiative, info, taskstatus):
    print("Trying to print the content")
    if initiative == "" and info == "":
        print("No Content")
        return f"Task Status: {taskstatus}"
    elif info == "":
        print("Only Initiative")
        return f"Initiative: {initiative} \nTask Status: {taskstatus}"
    elif initiative == "":
        print("Only info")
        return info
    else:
        print("All info")
        return f"Initiative: {initiative} \nTask Status: {taskstatus} \n{info}"

#METHOD TO MAKE A CALENDAR EVENT - DIFFERENT TIME CONDITIONS
def makeCalEvent(exist_eventId, eventName, eventDescription, eventStartTime, sourceURL, eventEndTime, newCalId, oldCalId, location):
    print("Convert Notion date type to Google calendar format: ", eventName)
    
    datetime_type = 0
    
    #Case 1: one-day allday event
    #Would you like to convert notion's allday event to GCal event with default of 8 am - 9 am?
    if eventStartTime.hour == 0 and eventStartTime.minute == 0 and eventEndTime == eventStartTime:
        #Yes
        if AllDayEventOption == 1:
            datetime_type = 1 #mark as datetime format
            eventStartTime = datetime.combine(eventStartTime, datetime.min.time()) + timedelta(hours=DEFAULT_EVENT_START)
            eventEndTime = eventStartTime + timedelta(minutes= DEFAULT_EVENT_LENGTH)
        #No
        else:
            eventEndTime = eventEndTime + timedelta(days=1)
    #Case 2: cross-day allday event
    elif eventStartTime.hour == 0 and eventStartTime.minute ==  0 and eventEndTime.hour == 0 and eventEndTime.minute == 0 and eventStartTime != eventEndTime:
        eventEndTime = eventEndTime + timedelta(days=1)
    #Case 3: Not allday event
    else:
        datetime_type = 1 #mark as datetime format
        #Start time == end time or NO end time
        if eventEndTime == eventStartTime or eventEndTime == None: 
            eventStartTime = eventStartTime
            eventEndTime = eventStartTime + timedelta(minutes= DEFAULT_EVENT_LENGTH) 
        #if you give a specific start time to the event
        else: 
            eventStartTime = eventStartTime
            eventEndTime = eventEndTime
        
    # write into Event: date or datetime
    if datetime_type == 1:       
        event = {
            "summary": eventName,
            "location": location,
            "description": eventDescription,
            "start": {
                "dateTime": eventStartTime.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": eventEndTime.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": timezone,
            }, 
            "source": {
                "title": "Notion Link",
                "url": sourceURL,
            }
        }  
    else:
        event = {
            "summary": eventName,
            "description": eventDescription,
            "start": {
                "date": eventStartTime.strftime("%Y-%m-%d"),
                "timeZone": timezone,
            },
            "end": {
                "date": eventEndTime.strftime("%Y-%m-%d"),
                "timeZone": timezone,
            }, 
            "source": {
                "title": "Notion Link",
                "url": sourceURL,
            }
        }
    
    if exist_eventId == "":
        x = service.events().insert(calendarId=newCalId, body=event).execute()
    else:
        if newCalId == oldCalId:
            x = service.events().update(calendarId=newCalId, eventId=exist_eventId, body=event).execute()
        else: #When we have to move the event to a new calendar. We must move the event over to the new calendar and then update the information on the event
            print(f'Move {eventName} from {calendarDictionary_trans[oldCalId]} Cal to {calendarDictionary_trans[newCalId]} Cal')
            print("\n")
            # move
            x = service.events().move(calendarId=oldCalId, eventId=exist_eventId, destination=newCalId).execute()
            # update
            x = service.events().update(calendarId=newCalId, eventId = exist_eventId, body=event).execute()
    return x["id"]

#METHOD TO MAKE A EVENT ID LIST
def queryGCalId(id, num=300):
    x = service.events().list(calendarId = id, maxResults = num, timeMin = google_timemin, timeMax = google_timemax).execute()
    return x


#######################################
##### The Method Section - Notion #####
#######################################
#Notion time format
def notion_time():
    return datetime.now().strftime(f"%Y-%m-%dT%H:%M:%S{timecode}")

#Find GCal Eevnt IDs
def all_notion_eventid(which):
    #get all notion events
    ALL_notion_gCal_Ids = []
    ALL_notion_gCal_Ids_pageid = {}
    resultList = queryNotionEvent_gcal()
    print("\n")
    print(f"{which} | Get all Notion event")
    for result in resultList: 
        GCalId = result["properties"][GCalEventId_Notion_Name]["rich_text"][0]["text"]["content"]
        ALL_notion_gCal_Ids.append(GCalId)
        ALL_notion_gCal_Ids_pageid[GCalId] = result["id"]
    return ALL_notion_gCal_Ids, ALL_notion_gCal_Ids_pageid
   
#Find data in Notion database
#time range + not delete
def queryNotionEvent_all():
    my_page = notion.databases.query(
        **{
            "database_id": database_id, 
            "filter": {
                "and": [
                    {
                        "and": [
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_before": before_date
                            }
                        },
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_after": after_date
                            }
                        }
                    ]   
                    },
                    {
                        "property": Delete_Notion_Name, 
                        "checkbox":  {
                            "equals": False
                        }
                    }
                ]
            }
        }
    )
    return my_page["results"]

#Find data in Notion database
#not on gcal or needupdate + time range + not delete
def queryNotionEvent_notion():
    my_page = notion.databases.query(
        **{
            "database_id": database_id, 
            "filter": {
                "and": [
                    {
                        "or": [
                        {
                            "property": On_GCal_Notion_Name, 
                            "checkbox":  {
                                "equals": False
                            }
                        },
                        {
                            "property": NeedGCalUpdate_Notion_Name, 
                            "formula":{
                                "checkbox":  {
                                    "equals": True
                                }
                            }
                        }
                    ]   
                    },
                    {
                        "and": [
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_before": before_date
                            }
                        },
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_after": after_date
                            }
                        }
                    ]   
                    },
                    {
                        "property": Delete_Notion_Name, 
                        "checkbox":  {
                            "equals": False
                        }
                    }
                ]
            },
        }
    )
    return my_page["results"]

#Find data in Notion database
#not on gcal or needupdate + time range + not delete
def queryNotionEvent_page(id): #bug
    my_page = notion.databases.query(
        **{
            "database_id": database_id,
            "filter": {
                "and":[
                    {
                        "property": Page_ID_Notion_Name, 
                        "formula":{
                            "string":  {
                                "equals": id
                            }
                        }
                    },
                    {
                        "property": Delete_Notion_Name, 
                        "checkbox":  {
                            "equals": False
                        }
                    }
                ]
            },
        }
    )
    resultList = my_page["results"]
    print(f"Page Query: {resultList}")

#Find data in Notion database
#on gcal + not delete + time range
def queryNotionEvent_gcal():
    my_page = notion.databases.query(  
        **{
            "database_id": database_id, 
            "filter": {
                "and": [
                    {
                        "property": On_GCal_Notion_Name, 
                        "checkbox":  {
                            "equals": True
                        }
                    },
                    {
                        "property": Delete_Notion_Name, 
                        "checkbox":  {
                            "equals": False
                        }
                    },
                    {
                        "and": [
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_before": before_date
                            }
                        },
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_after": after_date
                            }
                        }
                    ]    
                    },
                ]
            },
        }
    )
    return my_page["results"]

#Find data in Notion database
#on gcal*2 + delete
def queryNotionEvent_delete():
    my_page = notion.databases.query( 
        **{
            "database_id": database_id,
            "filter": {
                "and":[
                    {
                        "property": On_GCal_Notion_Name, 
                        "checkbox":  {
                            "equals": True
                        }
                    },
                    {
                        "property": Delete_Notion_Name, 
                        "checkbox":  {
                            "equals": True
                        }
                    },
                    {
                        "and": [
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_before": before_date
                            }
                        },
                        {
                            "property": Date_Notion_Name, 
                            "date": {
                                "on_or_after": after_date
                            }
                        }
                    ]   
                    }
                ]
            },
        }
    )

    return my_page["results"]

#Update Google Status
def updateGStatus(id):            
    my_page = notion.pages.update( 
        **{
            "page_id": id, 
            "properties": {
                On_GCal_Notion_Name: {
                    "checkbox": True 
                },
                LastUpdatedTime_Notion_Name: {
                    "date":{
                        "start": notion_time(),
                        "end": None,
                    }
                },
            },
        },
    )

#Update Default Google Cal Link to Notion
def updateDefaultCal(id, gcal, gcalid):
    my_page = notion.pages.update( 
        **{
            "page_id": id, 
            "properties": {
                GCalEventId_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gcal
                        }
                    }]
                },
                Current_Calendar_Id_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gcalid
                        }
                    }]
                },
                Calendar_Notion_Name:  { 
                    "select": {
                        "name": DEFAULT_CALENDAR_NAME
                    },
                },
            },
        },
    ) 

#Update Google Cal Link to Notion
def updateCal(id, gcal, gcalid):
    my_page = notion.pages.update(
        **{
            "page_id": id, 
            "properties": {
                GCalEventId_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gcal
                        }
                    }]
                },
                Current_Calendar_Id_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gcalid
                        }
                    }]
                }
            },
        },
    )         
            
#Delete Google Information
def deleteGInfo(id):
    clear_property = ""
    my_page = notion.pages.update( 
        **{
            "page_id": id, 
            "properties": {
                On_GCal_Notion_Name: {
                    "checkbox": False 
                },
                LastUpdatedTime_Notion_Name: {
                    "date":{
                        "start": notion_time(),
                        "end": None,
                    }
                },
                GCalEventId_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": clear_property
                        }
                    }]
                },
                Current_Calendar_Id_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": clear_property
                        }
                    }]
                }
            }
        }
    )
    return my_page

#Create Notion page
def create_page(calname, calstartdate, calenddate, caldescription, calid, gCal_id, gCal_name, callocation):
    my_page = notion.pages.create(
        **{
            "parent": {
                "database_id": database_id,
            },
            "properties": {
                Task_Notion_Name: {
                    "type": "title",
                    "title": [
                    {
                        "type": "text",
                        "text": {
                        "content": calname,
                        },
                    },
                    ],
                },
                Date_Notion_Name: {
                    "type": "date",
                    "date": {
                        "start": calstartdate,
                        "end": calenddate, 
                    }
                },
                LastUpdatedTime_Notion_Name: {
                    "type": "date",
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    }
                },
                ExtraInfo_Notion_Name:  {
                    "type": "rich_text", 
                    "rich_text": [{
                        "text": {
                            "content": caldescription
                        }
                    }]
                },
                Location_Notion_Name:  {
                    "type": "rich_text", 
                    "rich_text": [{
                        "text": {
                            "content": callocation
                        }
                    }]
                },
                GCalEventId_Notion_Name: {
                    "type": "rich_text", 
                    "rich_text": [{
                        "text": {
                            "content": calid
                        }
                    }]
                }, 
                On_GCal_Notion_Name: {
                    "type": "checkbox", 
                    "checkbox": True
                },
                Current_Calendar_Id_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gCal_id
                        }
                    }]
                },
                Calendar_Notion_Name:  { 
                    "select": {
                        "name": gCal_name
                    },
                }
            },
        },
    )
    print(f"Added this event to Notion: {calname}")
    print(f"From {calstartdate} to {calenddate}")
    
#Update Notion page: plus event name, event id, info
def update_page_all(pageid, calname, calstartdate, calenddate, caldescription, calid, gCal_id, gCal_name, callocation):
    my_page = notion.pages.update(
        **{
            "page_id": pageid,
            "properties": {
                Task_Notion_Name: {
                    "type": "title",
                    "title": [
                    {
                        "type": "text",
                        "text": {
                        "content": calname,
                        },
                    },
                    ],
                },
                Date_Notion_Name: {
                    "type": "date",
                    "date": {
                        "start": calstartdate,
                        "end": calenddate, 
                    }
                },
                LastUpdatedTime_Notion_Name: {
                    "type": "date",
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    }
                },
                ExtraInfo_Notion_Name:  {
                    "type": "rich_text", 
                    "rich_text": [{
                        "text": {
                            "content": caldescription
                        }
                    }]
                },
                Location_Notion_Name:  {
                    "type": "rich_text", 
                    "rich_text": [{
                        "text": {
                            "content": callocation
                        }
                    }]
                },
                GCalEventId_Notion_Name: {
                    "type": "rich_text", 
                    "rich_text": [{
                        "text": {
                            "content": calid
                        }
                    }]
                }, 
                On_GCal_Notion_Name: {
                    "type": "checkbox", 
                    "checkbox": True
                },
                Current_Calendar_Id_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gCal_id
                        }
                    }]
                },
                Calendar_Notion_Name:  { 
                    "select": {
                        "name": gCal_name
                    },
                }
            },
        },
    )
    print(f"Updated this event to Notion: {calname}")
    print(f"From {calstartdate} to {calenddate}")

#Update Notion page: only time, cal name, cal id
def update_page_time(pageid, calname, calstartdate, calenddate, gCal_id, gCal_name):
    my_page = notion.pages.update(
        **{
            "page_id": pageid,
            "properties": {
                Date_Notion_Name: {
                    "type": "date",
                    "date": {
                        "start": calstartdate,
                        "end": calenddate, 
                    }
                },
                LastUpdatedTime_Notion_Name: {
                    "type": "date",
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    }
                },
                On_GCal_Notion_Name: {
                    "type": "checkbox", 
                    "checkbox": True
                },
                Current_Calendar_Id_Notion_Name: {
                    "rich_text": [{
                        "text": {
                            "content": gCal_id
                        }
                    }]
                },
                Calendar_Notion_Name:  { 
                    "select": {
                        "name": gCal_name
                    },
                }
            },
        },
    )
    print(f"Updated this event to Notion: {calname}")
    print(f"From {calstartdate} to {calenddate}")


##############################################
#####     1. Add/Update Notion to GCal   #####
##############################################
def notion_to_gcal(action=0):

    if action == 1:
        #get all notion events
        ALL_notion_gCal_Ids, ALL_notion_gCal_Ids_pageid = all_notion_eventid("notion_to_gcal")
        #get all google events
        calItems = all_gcal_eventid("notion_to_gcal")
        
        calIds = []
        for calItem in calItems:
            calIds.append(calItem["id"])
            
        print("\n")
        print("notion_to_gcal | Compare google event id vs notion event id")
        print(calIds)
        print("\n")
        print(ALL_notion_gCal_Ids)
        print("\n")
        
        resultLists = []
        for i, el in enumerate(ALL_notion_gCal_Ids):
            if el not in calIds:
                #query the database
                resultList = queryNotionEvent_page(el)
                resultLists.append(resultList)
                print(resultList)
                #issue 
                #bug
                sys.exit(1)
    else:
        #query the database
        resultList = queryNotionEvent_notion()
    
    TaskNames = [] #1
    start_Dates = [] #2
    end_Times = [] #3
    Initiatives = [] #4
    ExtraInfo = [] #5
    TaskStatus = [] #6
    URL_list = [] #7
    calEventIdList = [] #8
    CalendarList = [] #9
    Locations = [] #10


    if len(resultList) > 0:
        i = len(resultList)
        print(f"---- {i} EVENTS: RUNNING NOTIONSYNC NOW | Change in Notion to Gcalendar ----")
        
        for i, el in enumerate(resultList):
            print(f"---- {i} th Result ready to be updated to google calendar ----")

            #1
            try:
                event_0 = el["properties"][CompleteIcon_Notion_Name]["formula"]["string"]
                event_1 = el["properties"][Task_Notion_Name]["title"][0]["text"]["content"]
                event = event_0 + event_1
                print(event)
                TaskNames.append(event)
            except:
                event_0 = "❓"
                event_1 = el["properties"][Task_Notion_Name]["title"][0]["text"]["content"]
                event = event_0 + event_1
                print(event)
                TaskNames.append(event)
                
            #2
            event_2 = el["properties"][Date_Notion_Name]["date"]["start"]
            start_Dates.append(event_2)
            print(event_2)
            #3
            if el["properties"][Date_Notion_Name]["date"]["end"] != None:
                event_3 = el["properties"][Date_Notion_Name]["date"]["end"]
                print(event_3)
                end_Times.append(event_3)
            else:
                event_3 = el["properties"][Date_Notion_Name]["date"]["start"]
                print(event_3)
                end_Times.append(event_3)
            #4
            try:
                # multiple choice
                if len(el["properties"][Initiative_Notion_Name]["multi_select"]) > 1:
                    firstInitiative = el["properties"][Initiative_Notion_Name]["multi_select"][0]["name"]
                    mulInitiative = firstInitiative + "...etc."
                    Initiatives.append(mulInitiative)
                # single choice
                else:
                    Initiatives.append(el["properties"][Initiative_Notion_Name]["multi_select"][0]["name"])
            except:
                Initiatives.append("")
            #5
            try:
                event_5 = el["properties"][ExtraInfo_Notion_Name]["rich_text"][0]["text"]["content"]
                print(event_5)
                ExtraInfo.append(event_5)
            except:
                print("No Extra Info")
                ExtraInfo.append("")
            #6
            try:
                event_6 = el["properties"][Status_Notion_Name]["select"]["name"]
                print(event_6)
                TaskStatus.append(event_6)
            except:
                print("No Status")
                TaskStatus.append("")
            #7
            URL_list.append(makeTaskURL(el["id"], urlRoot))
            #8
            try:
                event_8 = el["properties"][Calendar_Notion_Name]["select"]["name"]
                CalendarList.append(calendarDictionary[event_8])
            except: #keyerror occurs when there's nothing put into the calendar in the first place
                CalendarList.append(DEFAULT_CALENDAR_ID)       
            #9
            try:
                event_10 = el["properties"][Location_Notion_Name]["rich_text"][0]["text"]["content"]
                print(event_10)
                Locations.append(event_10)
            except:
                print("No Location Info")
                Locations.append("")
                
            # get cal event id?
            try:
                exist_EventId = el["properties"][GCalEventId_Notion_Name]["rich_text"][0]["text"]["content"]
            except:
                exist_EventId = ""

            # check if users change the calendar
            currentCal = ""
            try:
                currentCal = el["properties"][Current_Calendar_Id_Notion_Name]["rich_text"][0]["text"]["content"]
            except:
                if exist_EventId != "":
                    print("Check the invalid event Id: {TaskNames[i]}")
                    sys.exit(1)

            # get each page id
            pageId = el["id"]
            
            # notion data will be writen into GCal, update the GCal Status first
            updateGStatus(pageId)

            # make Google event
            try:
                print("Date: start and end are both dates")
                calEventId = makeCalEvent(
                    exist_EventId, TaskNames[i], makeEventDescription(Initiatives[i], ExtraInfo[i], TaskStatus[i]), 
                    datetime.strptime(start_Dates[i], "%Y-%m-%d"), URL_list[i], 
                    datetime.strptime(end_Times[i], "%Y-%m-%d"), CalendarList[i], currentCal, Locations[i])
            except:
                print("Date: start and end are both date plus time")
                calEventId = makeCalEvent(
                    exist_EventId, TaskNames[i], makeEventDescription(Initiatives[i], ExtraInfo[i], TaskStatus[i]), 
                    datetime.strptime(start_Dates[i][:-6], "%Y-%m-%dT%H:%M:%S.000"), URL_list[i],  
                    datetime.strptime(end_Times[i][:-6], "%Y-%m-%dT%H:%M:%S.000"), CalendarList[i], currentCal, Locations[i])
                    
            
            calEventIdList.append(calEventId)
            
            #this means that there is no calendar assigned on Notion
            if CalendarList[i] == DEFAULT_CALENDAR_ID:
                updateDefaultCal(pageId, calEventIdList[i], CalendarList[i])

            else: #just a regular update
                updateCal(pageId, calEventIdList[i], CalendarList[i])
    
    else:
        print("Result List is empty. Nothing new from Notion to be added to GCal")


##############################################
#####     2. Add/Update GCal to Notion   #####
##############################################
def gcal_to_notion(action=0):
    #get all notion events
    ALL_notion_gCal_Ids, ALL_notion_gCal_Ids_pageid = all_notion_eventid("gcal_to_notion")
    #get all google events
    calItems = all_gcal_eventid("gcal_to_notion")

    calIds = [] #Event ID
    calNames = [] #Event Name
    gCal_calendarId = [] #Calendar ID
    gCal_calendarName = [] #Calendar Name
    calStartDates = [] #try: time format
    calEndDates = [] #try: time format
    calDescriptions = [] #try: add description
    calLocations = [] #try: add location
    print("\n")
    print("gcal_to_notion | Adj google time format")
    for calItem in calItems:
        calIds.append(calItem["id"])
        calNames.append(calItem["summary"])
        
        organizer_email = calItem["organizer"]["email"]
        gCal_calendarId.append(organizer_email)
        
        
        try:
            gCal_calendarName.append(calItem["organizer"]["displayName"])
        except:
            gCal_calendarName.append(calendarDictionary_trans[organizer_email])
        try:#start datetime
            calStartDates.append(datetime.strptime(calItem["start"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S"))
        except:#start date
            date = datetime.strptime(calItem["start"]["date"], "%Y-%m-%d")
            x = datetime(date.year, date.month, date.day, 0, 0, 0)
            calStartDates.append(x)
        try:#end datetime
            calEndDates.append(datetime.strptime(calItem["end"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S"))
        except:#end date
            date = datetime.strptime(calItem["end"]["date"], "%Y-%m-%d")
            x = datetime(date.year, date.month, date.day, 0, 0, 0)
            calEndDates.append(x)
        try:#add description
            withLocation = calItem["description"] + "\n" + "Location: " + calItem["location"]
            calDescriptions.append(withLocation)
        except:
            try:
                calDescriptions.append(calItem["description"])
            except:
                try:
                    calDescriptions.append(calItem["location"])
                except:
                    calDescriptions.append(" ")
        try:#add location
            calLocations.append(calItem["location"])
        except:
            calLocations.append("No Location Info")
    
    print("\n")
    print("gcal_to_notion | Compare google event id vs notion event id")
    print(calIds)
    print("\n")
    print(ALL_notion_gCal_Ids)
    print("\n")
    # Compare google event id vs notion event id
    for i in range(len(calIds)):
        if calStartDates[i] == calEndDates[i] - timedelta(days=1):
            calStartDate = calStartDates[i].strftime("%Y-%m-%d")
            calEndDate = None
        elif calStartDates[i].hour == 0 and calStartDates[i].minute == 0 and calEndDates[i].hour == 0 and calEndDates[i].minute == 0:
            calStartDate = calStartDates[i].strftime("%Y-%m-%d")
            calEndDate = (calEndDates[i] - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            calStartDate = DateTimeIntoNotionFormat(calStartDates[i])
            calEndDate = DateTimeIntoNotionFormat(calEndDates[i])
        #Create a page or Update a page?
        if calIds[i] in ALL_notion_gCal_Ids:
            if action == 2: #Overwrite notion
                print("--- Update events | Including name, description and calid from GCal to Notion ---")
                pageid = ALL_notion_gCal_Ids_pageid[calIds[i]]
                update_page_all(pageid, calNames[i], calStartDate, calEndDate, calDescriptions[i], 
                            calIds[i], gCal_calendarId[i], gCal_calendarName[i], calLocations[i])
            else:
                if action == 0: #default, update the timeslot and create the events which are not in notion
                    print("----------------- Update events' time slot from GCal to Notion ------------------")
                    pageid = ALL_notion_gCal_Ids_pageid[calIds[i]]
                    update_page_time(pageid, calNames[i], calStartDate, calEndDate, gCal_calendarId[i], gCal_calendarName[i])
        else: #create the event on notion
            print("----------- Create events (not in Notion already) from GCal to Notion -----------")
            create_page(calNames[i], calStartDate, calEndDate, calDescriptions[i], 
                        calIds[i], gCal_calendarId[i], gCal_calendarName[i], calLocations[i])
                    
    print("\n")


####################################################
########   Google deleted items by Notion   #######
####################################################
def deleteEvent():
    print("\n")
    print("-------- Deletion | Done? == True in Notion, delete the GCal event --------")
    resultList = queryNotionEvent_delete()

    if DELETE_OPTION == 0 and len(resultList) > 0:
        for i, el in enumerate(resultList):
            
            #make sure that"s what you want
            summary=el["properties"]["Task Name"]["title"][0]["text"]["content"]
            pageId = el["id"]
            calendarID = calendarDictionary[el["properties"][Calendar_Notion_Name]["select"]["name"]]
            try:
                eventId = el["properties"][GCalEventId_Notion_Name]["rich_text"][0]["text"]["content"]
            except:
                print(f"{summary} does not have event ID. Make sure that it exists in Notion")
                os._exit(1)
            print(f"{i}th 正在處理的GCal Event {summary}, EventID {eventId}")
            
            try: #delete Gcal event
                service.events().delete(calendarId=calendarID, eventId=eventId).execute()
                print(f"{i}th 正在刪除的GCal Event {summary}, EventID {eventId}")
            except:
                continue
            
            #delete google event id and Cal id in Notion
            deleteGInfo(pageId)
    else:
        print("---------------------- No deleted the GCal event ----------------------")
    
    
####################################################
########           One Event Sample          #######
####################################################
def notion_event_sample(num=1):
    count = 0
    resultList = queryNotionEvent_all()
    if len(resultList) > 1:
        for i, el in enumerate(resultList):  
            if count < num:
                count = count + 1
                print(f"{i}th Query Notion Event")
                print(el)
                print("\n")
            
def gcal_event_sample(name=DEFAULT_CALENDAR_NAME, num=1):
    calendarID = "" #input manually
    eventID = "" #input manually
    events = service.events().list(calendarId=calendarID).execute()
    if eventID != "":
        for i, el in enumerate(events['items']):
            if el['id'] == eventID:
                print(f"Find {eventID}")
                print(events['items'][i]['location'])
                break
    else:
        print(events['items'][num])