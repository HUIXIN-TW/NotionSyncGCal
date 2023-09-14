import os
import sys
import json
from datetime import datetime, timedelta


import gcal_token
import notion_token

try:
    nt = notion_token.Notion()
    print("--- Notion activated ---")
    ##### The Set-Up Section - GCal #####
    GOOGLE_SERVICE = gcal_token.Google()
    print(f"--- {GOOGLE_SERVICE.service} ---")
    print(f"--- Google activated ---")
    print("\n")
    print("################################## START ##################################")
    print("###########################################################################")
    print(
        f"--- Run sync.py | After {nt.AFTER_DATE} Included, Before {nt.BEFORE_DATE} Not Included ---"
    )
except Exception as e:
    print(e)
    print("--- Exit sync.py ---")
    sys.exit()

#######################################
##### The Method Section - Google #####
#######################################
# METHOD TO FIND GCAL EVENT IDs


def all_gcal_eventid(which):
    # get all google events
    print("\n")
    print(f"{which} | Get all Google event")
    events = []  # contains all cals and their tasks
    for calid in nt.GCAL_DIC.values():
        x = queryGCalId(calid)
        events.extend(x["items"])
    return events


# METHOD TO MAKE GOOGLE TIME FORMAT TO NOTION


def DateTimeIntoNotionFormat(dateTimeValue):
    return dateTimeValue.strftime(f"%Y-%m-%dT%H:%M:%S{nt.TIMECODE}")


# METHOD TO MAKE A NOTION URL


def makeTaskURL(
    ending, urlRoot
):  # urlRoot: Notion Page Prefix, ending: Notion Page Suffix
    urlId = ending.replace("-", "")
    return urlRoot + urlId  # Notion Page ID


# METHOD TO MAKE A CALENDAR EVENT DESCRIPTION


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


# METHOD TO MAKE A CALENDAR EVENT - DIFFERENT TIME CONDITIONS


def makeCalEvent(
    exist_eventId,
    eventName,
    eventDescription,
    eventlocation,
    eventStartTime,
    eventEndTime,
    newCalId,
    oldCalId,
    sourceURL,
    skip,
):
    print("Convert Notion date type to Google calendar format: ", eventName)

    datetime_type = 0

    # Case 1: one-day allday event
    # Would you like to convert notion's allday event to GCal event with default of 8 am - 9 am?
    if (
        eventStartTime.hour == 0
        and eventStartTime.minute == 0
        and eventEndTime == eventStartTime
    ):
        # Yes
        if nt.ALLDAY_OPTION == 1:
            datetime_type = 1  # mark as datetime format
            eventStartTime = datetime.combine(
                eventStartTime, datetime.min.time()
            ) + timedelta(hours=nt.DEFAULT_EVENT_START)
            eventEndTime = eventStartTime + timedelta(minutes=nt.DEFAULT_EVENT_LENGTH)
        # No
        else:
            eventEndTime = eventEndTime + timedelta(days=1)
    # Case 2: cross-day allday event
    elif (
        eventStartTime.hour == 0
        and eventStartTime.minute == 0
        and eventEndTime.hour == 0
        and eventEndTime.minute == 0
        and eventStartTime != eventEndTime
    ):
        eventEndTime = eventEndTime + timedelta(days=1)
    # Case 3: Not allday event
    else:
        datetime_type = 1  # mark as datetime format
        # Start time == end time or NO end time
        if eventEndTime == eventStartTime or eventEndTime == None:
            eventStartTime = eventStartTime
            eventEndTime = eventStartTime + timedelta(minutes=nt.DEFAULT_EVENT_LENGTH)
        # if you give a specific start time to the event
        else:
            eventStartTime = eventStartTime
            eventEndTime = eventEndTime

    # write into Event: date or datetime
    if skip == 1:  # can skip some information if you want to
        event = {
            "summary": eventName,
            "location": eventlocation,
            "description": eventDescription,
            "start": {
                "dateTime": eventStartTime.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": nt.TIMEZONE,
            },
            "end": {
                "dateTime": eventEndTime.strftime("%Y-%m-%dT%H:%M:%S"),
                "timeZone": nt.TIMEZONE,
            },
            "source": {
                "title": "Notion Link",
                "url": sourceURL,
            },
        }
    else:
        if datetime_type == 1:
            event = {
                "summary": eventName,
                "location": eventlocation,
                "description": eventDescription,
                "start": {
                    "dateTime": eventStartTime.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": nt.TIMEZONE,
                },
                "end": {
                    "dateTime": eventEndTime.strftime("%Y-%m-%dT%H:%M:%S"),
                    "timeZone": nt.TIMEZONE,
                },
                "source": {
                    "title": "Notion Link",
                    "url": sourceURL,
                },
            }
        else:
            event = {
                "summary": eventName,
                "location": eventlocation,
                "description": eventDescription,
                "start": {
                    "date": eventStartTime.strftime("%Y-%m-%d"),
                    "timeZone": nt.TIMEZONE,
                },
                "end": {
                    "date": eventEndTime.strftime("%Y-%m-%d"),
                    "timeZone": nt.TIMEZONE,
                },
                "source": {
                    "title": "Notion Link",
                    "url": sourceURL,
                },
            }

    if exist_eventId == "":
        x = (
            GOOGLE_SERVICE.service.events()
            .insert(calendarId=newCalId, body=event)
            .execute()
        )
    else:
        if newCalId == oldCalId:
            x = (
                GOOGLE_SERVICE.service.events()
                .update(calendarId=newCalId, eventId=exist_eventId, body=event)
                .execute()
            )
        else:  # When we have to move the event to a new calendar. We must move the event over to the new calendar and then update the information on the event
            print(
                f"Move {eventName} from {nt.GCAL_DIC_KEY_TO_VALUE[oldCalId]} Cal to {nt.GCAL_DIC_KEY_TO_VALUE[newCalId]} Cal"
            )
            print("\n")
            # move
            x = (
                GOOGLE_SERVICE.service.events()
                .move(calendarId=oldCalId, eventId=exist_eventId, destination=newCalId)
                .execute()
            )
            # update
            x = (
                GOOGLE_SERVICE.service.events()
                .update(calendarId=newCalId, eventId=exist_eventId, body=event)
                .execute()
            )
    return x["id"]


# METHOD TO MAKE A EVENT ID LIST


def queryGCalId(id, num=300):
    x = (
        GOOGLE_SERVICE.service.events()
        .list(
            calendarId=id,
            maxResults=num,
            timeMin=nt.GOOGLE_TIMEMIN,
            timeMax=nt.GOOGLE_TIMEMAX,
        )
        .execute()
    )
    return x


#######################################
##### The Method Section - Notion #####
#######################################
# Notion time format
def notion_time():
    return datetime.now().strftime(f"%Y-%m-%dT%H:%M:%S{nt.TIMECODE}")


# Find GCal Eevnt IDs


def all_notion_eventid(which):
    # get all notion events
    ALL_notion_gCal_Ids = []
    ALL_notion_gCal_Ids_pageid = {}
    resultList = queryNotionEvent_gcal()
    print("\n")
    print(f"{which} | Get all Notion event")
    for result in resultList:
        GCalId = result["properties"][nt.GCALEVENTID_NOTION_NAME]["rich_text"][0][
            "text"
        ]["content"]
        ALL_notion_gCal_Ids.append(GCalId)
        ALL_notion_gCal_Ids_pageid[GCalId] = result["id"]
    return ALL_notion_gCal_Ids, ALL_notion_gCal_Ids_pageid


# Find data in Notion database
# time range + not delete


def queryNotionEvent_all():
    my_page = nt.NOTION.databases.query(
        **{
            "database_id": nt.DATABASE_ID,
            "filter": {
                "and": [
                    {
                        "and": [
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_before": nt.BEFORE_DATE},
                            },
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_after": nt.AFTER_DATE},
                            },
                        ]
                    },
                    {"property": nt.DELETE_NOTION_NAME, "checkbox": {"equals": False}},
                ]
            },
        }
    )
    return my_page["results"]


# Find data in Notion database
# not on gcal or needupdate + time range + not delete


def queryNotionEvent_notion():
    my_page = nt.NOTION.databases.query(
        **{
            "database_id": nt.DATABASE_ID,
            "filter": {
                "and": [
                    {
                        "or": [
                            {
                                "property": nt.ON_GCAL_NOTION_NAME,
                                "checkbox": {"equals": False},
                            },
                            {
                                "property": nt.NEEDGCALUPDATE_NOTION_NAME,
                                "formula": {"checkbox": {"equals": True}},
                            },
                        ]
                    },
                    {
                        "and": [
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_before": nt.BEFORE_DATE},
                            },
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_after": nt.AFTER_DATE},
                            },
                        ]
                    },
                    {"property": nt.DELETE_NOTION_NAME, "checkbox": {"equals": False}},
                ]
            },
        }
    )
    return my_page["results"]


# Find data in Notion database
# not on gcal or needupdate + time range + not delete


def queryNotionEvent_page(id):  # bug
    my_page = nt.NOTION.databases.query(
        **{
            "database_id": nt.DATABASE_ID,
            "filter": {
                "and": [
                    {
                        "property": nt.PAGE_ID_NOTION_NAME,
                        "formula": {"string": {"equals": id}},
                    },
                    {"property": nt.DELETE_NOTION_NAME, "checkbox": {"equals": False}},
                ]
            },
        }
    )
    resultList = my_page["results"]
    print(f"Page Query: {resultList}")


# Find data in Notion database
# on gcal + not delete + time range


def queryNotionEvent_gcal():
    my_page = nt.NOTION.databases.query(
        **{
            "database_id": nt.DATABASE_ID,
            "filter": {
                "and": [
                    {"property": nt.ON_GCAL_NOTION_NAME, "checkbox": {"equals": True}},
                    {"property": nt.DELETE_NOTION_NAME, "checkbox": {"equals": False}},
                    {
                        "and": [
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_before": nt.BEFORE_DATE},
                            },
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_after": nt.AFTER_DATE},
                            },
                        ]
                    },
                ]
            },
        }
    )
    return my_page["results"]


# Find data in Notion database
# on gcal*2 + delete


def queryNotionEvent_delete():
    my_page = nt.NOTION.databases.query(
        **{
            "database_id": nt.DATABASE_ID,
            "filter": {
                "and": [
                    {"property": nt.ON_GCAL_NOTION_NAME, "checkbox": {"equals": True}},
                    {"property": nt.DELETE_NOTION_NAME, "checkbox": {"equals": True}},
                    {
                        "and": [
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_before": nt.BEFORE_DATE},
                            },
                            {
                                "property": nt.DATE_NOTION_NAME,
                                "date": {"on_or_after": nt.AFTER_DATE},
                            },
                        ]
                    },
                ]
            },
        }
    )

    return my_page["results"]


# Update Google Status


def updateGStatus(id):
    my_page = nt.NOTION.pages.update(
        **{
            "page_id": id,
            "properties": {
                nt.ON_GCAL_NOTION_NAME: {"checkbox": True},
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    }
                },
            },
        },
    )


# Update Default Google Cal Link to Notion


def updateDefaultCal(id, gcal, gcalid):
    my_page = nt.NOTION.pages.update(
        **{
            "page_id": id,
            "properties": {
                nt.GCALEVENTID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gcal}}]
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gcalid}}]
                },
                nt.CALENDAR_NOTION_NAME: {
                    "select": {"name": nt.GCAL_DEFAULT_NAME},
                },
            },
        },
    )


# Update Google Cal Link to Notion


def updateCal(id, gcal, gcalid):
    my_page = nt.NOTION.pages.update(
        **{
            "page_id": id,
            "properties": {
                nt.GCALEVENTID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gcal}}]
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gcalid}}]
                },
            },
        },
    )


# Delete Google Information


def deleteGInfo(id):
    clear_property = ""
    my_page = nt.NOTION.pages.update(
        **{
            "page_id": id,
            "properties": {
                nt.ON_GCAL_NOTION_NAME: {"checkbox": False},
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    }
                },
                nt.GCALEVENTID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": clear_property}}]
                },
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": clear_property}}]
                },
            },
        }
    )
    return my_page


# Create Notion page


def create_page(
    calname,
    calstartdate,
    calenddate,
    caldescription,
    callocation,
    calid,
    gCal_id,
    gCal_name,
):
    my_page = nt.NOTION.pages.create(
        **{
            "parent": {
                "database_id": nt.DATABASE_ID,
            },
            "properties": {
                nt.TASK_NOTION_NAME: {
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
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": calstartdate,
                        "end": calenddate,
                    },
                },
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    },
                },
                nt.EXTRAINFO_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": caldescription}}],
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": callocation}}],
                },
                nt.GCALEVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": calid}}],
                },
                nt.ON_GCAL_NOTION_NAME: {"type": "checkbox", "checkbox": True},
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gCal_id}}]
                },
                nt.CALENDAR_NOTION_NAME: {
                    "select": {"name": gCal_name},
                },
            },
        },
    )
    print(f"Added this event to Notion: {calname}")
    print(f"From {calstartdate} to {calenddate}")


# Update Notion page: plus event name, event id, info


def update_page_all(
    pageid,
    calname,
    calstartdate,
    calenddate,
    caldescription,
    callocation,
    calid,
    gCal_id,
    gCal_name,
):
    my_page = nt.NOTION.pages.update(
        **{
            "page_id": pageid,
            "properties": {
                nt.TASK_NOTION_NAME: {
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
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": calstartdate,
                        "end": calenddate,
                    },
                },
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    },
                },
                nt.EXTRAINFO_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": caldescription}}],
                },
                nt.LOCATION_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": callocation}}],
                },
                nt.GCALEVENTID_NOTION_NAME: {
                    "type": "rich_text",
                    "rich_text": [{"text": {"content": calid}}],
                },
                nt.ON_GCAL_NOTION_NAME: {"type": "checkbox", "checkbox": True},
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gCal_id}}]
                },
                nt.CALENDAR_NOTION_NAME: {
                    "select": {"name": gCal_name},
                },
            },
        },
    )
    print(f"Updated this event to Notion: {calname}")
    print(f"From {calstartdate} to {calenddate}")


# Update Notion page: only time, cal name, cal id


def update_page_time(pageid, calname, calstartdate, calenddate, gCal_id, gCal_name):
    my_page = nt.NOTION.pages.update(
        **{
            "page_id": pageid,
            "properties": {
                nt.DATE_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": calstartdate,
                        "end": calenddate,
                    },
                },
                nt.LASTUPDATEDTIME_NOTION_NAME: {
                    "type": "date",
                    "date": {
                        "start": notion_time(),
                        "end": None,
                    },
                },
                nt.ON_GCAL_NOTION_NAME: {"type": "checkbox", "checkbox": True},
                nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
                    "rich_text": [{"text": {"content": gCal_id}}]
                },
                nt.CALENDAR_NOTION_NAME: {
                    "select": {"name": gCal_name},
                },
            },
        },
    )
    print(f"Updated this event to Notion: {calname}")
    print(f"From {calstartdate} to {calenddate}")


##############################################
#####     1. Add/Update Notion to GCal   #####
##############################################
def notion_to_gcal(action=0, updateEverything=True):
    if action == 1:
        # get all notion events
        ALL_notion_gCal_Ids, ALL_notion_gCal_Ids_pageid = all_notion_eventid(
            "notion_to_gcal"
        )
        # get all google events
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
        # for i, el in enumerate(ALL_notion_gCal_Ids):
        #     if el not in calIds:
        #         # query the database
        #         resultList = queryNotionEvent_page(el)
        #         resultLists.append(resultList)
        #         print(resultList)
        #         sys.exit(1)
    else:
        # query the database
        if updateEverything:
            resultList = queryNotionEvent_notion()
        else:
            resultList = queryNotionEvent_all()

    TaskNames = []  # 1
    start_Dates = []  # 2
    end_Times = []  # 3
    Initiatives = []  # 4
    ExtraInfo = []  # 5
    TaskStatus = []  # 6
    URL_list = []  # 7
    calEventIdList = []  # 8
    CalendarList = []  # 9
    Locations = []  # 10

    if len(resultList) > 0:
        n = len(resultList)
        print(
            f"---- {n} EVENTS: RUNNING NOTIONSYNC NOW | Change in Notion to Gcalendar ----"
        )

        for i, el in enumerate(resultList):
            print(f"---- {i} th Result ready to be updated to google calendar ----")
            # 1
            try:
                event_0 = el["properties"][nt.COMPLETEICON_NOTION_NAME]["formula"][
                    "string"
                ]
                event_1 = el["properties"][nt.TASK_NOTION_NAME]["title"][0]["text"][
                    "content"
                ]
                event = event_0 + event_1
                print(event)
                TaskNames.append(event)
            except:
                event_0 = "❓"
                event_1 = el["properties"][nt.TASK_NOTION_NAME]["title"][0]["text"][
                    "content"
                ]
                event = event_0 + event_1
                print(event)
                TaskNames.append(event)

            # 2
            event_2 = el["properties"][nt.DATE_NOTION_NAME]["date"]["start"]
            start_Dates.append(event_2)
            print(event_2)
            # 3
            if el["properties"][nt.DATE_NOTION_NAME]["date"]["end"] != None:
                event_3 = el["properties"][nt.DATE_NOTION_NAME]["date"]["end"]
                print(event_3)
                end_Times.append(event_3)
            else:
                event_3 = el["properties"][nt.DATE_NOTION_NAME]["date"]["start"]
                print(event_3)
                end_Times.append(event_3)
            # 4
            try:
                # multiple choice
                if len(el["properties"][nt.INITIATIVE_NOTION_NAME]["multi_select"]) > 1:
                    firstInitiative = el["properties"][nt.INITIATIVE_NOTION_NAME][
                        "multi_select"
                    ][0]["name"]
                    mulInitiative = firstInitiative + "...etc."
                    Initiatives.append(mulInitiative)
                # single choice
                else:
                    Initiatives.append(
                        el["properties"][nt.INITIATIVE_NOTION_NAME]["multi_select"][0][
                            "name"
                        ]
                    )
            except:
                Initiatives.append("")
            # 5
            try:
                event_5 = el["properties"][nt.EXTRAINFO_NOTION_NAME]["rich_text"][0][
                    "text"
                ]["content"]
                print(event_5)
                ExtraInfo.append(event_5)
            except:
                print("No Extra Info")
                ExtraInfo.append("")
            # 6
            try:
                event_6 = el["properties"][nt.STATUS_NOTION_NAME]["select"]["name"]
                print(event_6)
                TaskStatus.append(event_6)
            except:
                print("No Status")
                TaskStatus.append("")
            # 7
            URL_list.append(makeTaskURL(el["id"], nt.URLROOT))
            # 8
            try:
                event_8 = el["properties"][nt.CALENDAR_NOTION_NAME]["select"]["name"]
                CalendarList.append(nt.GCAL_DIC[event_8])
            except:  # keyerror occurs when there's nothing put into the calendar in the first place
                CalendarList.append(nt.GCAL_DEFAULT_ID)
            # 10
            try:
                event_10 = el["properties"][nt.LOCATION_NOTION_NAME]["rich_text"][0][
                    "text"
                ]["content"]
                Locations.append(event_10)
            except:
                Locations.append("")

            # get cal event id?
            try:
                exist_EventId = el["properties"][nt.GCALEVENTID_NOTION_NAME][
                    "rich_text"
                ][0]["text"]["content"]
            except:
                exist_EventId = ""

            # check if users change the calendar
            currentCal = ""
            try:
                currentCal = el["properties"][nt.CURRENT_CALENDAR_ID_NOTION_NAME][
                    "rich_text"
                ][0]["text"]["content"]
            except Exception as e:
                if exist_EventId != "":
                    errorTask = TaskNames[i]
                    print(f"Check the invalid event Id: {errorTask}")
                    print(e)
                    sys.exit(1)

            # get each page id
            pageId = el["id"]

            # notion data will be writen into GCal, update the GCal Status first
            updateGStatus(pageId)

            # subscription calendar
            try:
                subscribedCal_Id = el["properties"][nt.CURRENT_CALENDAR_ID_NOTION_NAME][
                    "rich_text"
                ][0]["text"]["content"]
                if "@import.calendar.google.com" in subscribedCal_Id:
                    subscribedCal_Name = el["properties"][nt.CALENDAR_NOTION_NAME][
                        "select"
                    ]["name"]
                    print(
                        f"---- {subscribedCal_Name} is subscription which can't be edited ----"
                    )
                    calEventIdList.append("")
                    continue
            except:
                print("Exclue subscript calendar")

            # make Google event
            skip = 0
            if (
                nt.SKIP_DESCRIPTION_CONDITION in TaskNames[i]
                and nt.SKIP_DESCRIPTION_CONDITION != ""
            ):
                skip = 1
            try:
                print("Date: start and end are both dates")
                calEventId = makeCalEvent(
                    exist_EventId,
                    TaskNames[i],
                    makeEventDescription(Initiatives[i], ExtraInfo[i], TaskStatus[i]),
                    Locations[i],
                    datetime.strptime(start_Dates[i], "%Y-%m-%d"),
                    datetime.strptime(end_Times[i], "%Y-%m-%d"),
                    CalendarList[i],
                    currentCal,
                    URL_list[i],
                    skip,
                )
            except:
                print("Date: start and end are both date plus time")
                calEventId = makeCalEvent(
                    exist_EventId,
                    TaskNames[i],
                    makeEventDescription(Initiatives[i], ExtraInfo[i], TaskStatus[i]),
                    Locations[i],
                    datetime.strptime(start_Dates[i][:-6], "%Y-%m-%dT%H:%M:%S.000"),
                    datetime.strptime(end_Times[i][:-6], "%Y-%m-%dT%H:%M:%S.000"),
                    CalendarList[i],
                    currentCal,
                    URL_list[i],
                    skip,
                )

            calEventIdList.append(calEventId)

            # this means that there is no calendar assigned on Notion
            if CalendarList[i] == nt.GCAL_DEFAULT_ID:
                updateDefaultCal(pageId, calEventIdList[i], CalendarList[i])

            else:  # just a regular update
                updateCal(pageId, calEventIdList[i], CalendarList[i])

    else:
        print("Result List is empty. Nothing new from Notion to be added to GCal")


##############################################
#####     2. Add/Update GCal to Notion   #####
##############################################
def gcal_to_notion(action=0):
    # get all notion events
    ALL_notion_gCal_Ids, ALL_notion_gCal_Ids_pageid = all_notion_eventid(
        "gcal_to_notion"
    )
    # get all google events
    calItems = all_gcal_eventid("gcal_to_notion")

    calIds = []  # Event ID
    calNames = []  # Event Name
    gCal_calendarId = []  # Calendar ID
    gCal_calendarName = []  # Calendar Name
    calStartDates = []  # try: time format
    calEndDates = []  # try: time format
    calDescriptions = []  # try: add description
    calLocations = []  # try: add location
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
            gCal_calendarName.append(nt.GCAL_DIC_KEY_TO_VALUE[organizer_email])
        try:  # start datetime
            calStartDates.append(
                datetime.strptime(
                    calItem["start"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S"
                )
            )
        except:  # start date
            date = datetime.strptime(calItem["start"]["date"], "%Y-%m-%d")
            x = datetime(date.year, date.month, date.day, 0, 0, 0)
            calStartDates.append(x)
        try:  # end datetime
            calEndDates.append(
                datetime.strptime(calItem["end"]["dateTime"][:-6], "%Y-%m-%dT%H:%M:%S")
            )
        except:  # end date
            date = datetime.strptime(calItem["end"]["date"], "%Y-%m-%d")
            x = datetime(date.year, date.month, date.day, 0, 0, 0)
            calEndDates.append(x)
        try:  # add description
            withLocation = (
                calItem["description"] + "\n" + "Location: " + calItem["location"]
            )
            calDescriptions.append(withLocation)
        except:
            try:
                calDescriptions.append(calItem["description"])
            except:
                try:
                    calDescriptions.append(calItem["location"])
                except:
                    calDescriptions.append(" ")
        try:  # add location
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
        elif (
            calStartDates[i].hour == 0
            and calStartDates[i].minute == 0
            and calEndDates[i].hour == 0
            and calEndDates[i].minute == 0
        ):
            calStartDate = calStartDates[i].strftime("%Y-%m-%d")
            calEndDate = (calEndDates[i] - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            calStartDate = DateTimeIntoNotionFormat(calStartDates[i])
            calEndDate = DateTimeIntoNotionFormat(calEndDates[i])
        # Create a page or Update a page?
        if calIds[i] in ALL_notion_gCal_Ids:
            if action == 2:  # Overwrite notion
                print(
                    f"--- Update events | Including name, description and calid from GCal to Notion {calNames[i]} {calStartDate} ---"
                )
                try:
                    pageid = ALL_notion_gCal_Ids_pageid[calIds[i]]
                    update_page_all(
                        pageid,
                        calNames[i],
                        calStartDate,
                        calEndDate,
                        calDescriptions[i],
                        calLocations[i],
                        calIds[i],
                        gCal_calendarId[i],
                        nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]],
                    )
                except:  # subscribe calendar
                    print(
                        f"This is a subscribed calendar - {nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]]}"
                    )
                    pageid = ALL_notion_gCal_Ids_pageid[calIds[i]]
                    update_page_all(
                        pageid,
                        calNames[i],
                        calStartDate,
                        calEndDate,
                        calDescriptions[i],
                        calLocations[i],
                        calIds[i],
                        gCal_calendarId[i],
                        nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]],
                    )
            else:
                if (
                    action == 0
                ):  # default, update the timeslot and create the events which are not in notion
                    print(
                        f"--- Update events' time slot from GCal to Notion {calNames[i]} {calStartDate} ---"
                    )
                    try:
                        pageid = ALL_notion_gCal_Ids_pageid[calIds[i]]
                        update_page_time(
                            pageid,
                            calNames[i],
                            calStartDate,
                            calEndDate,
                            gCal_calendarId[i],
                            nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]],
                        )
                    except:  # subscribe calendar
                        print(
                            f"This is a subscribed calendar - {nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]]}"
                        )
                        pageid = ALL_notion_gCal_Ids_pageid[calIds[i]]
                        update_page_time(
                            pageid,
                            calNames[i],
                            calStartDate,
                            calEndDate,
                            gCal_calendarId[i],
                            nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]],
                        )
        else:  # create the event on notion
            print(
                f"--- Create events (not in Notion already) from GCal to Notion {calNames[i]} {calStartDate} ---"
            )
            try:
                create_page(
                    calNames[i],
                    calStartDate,
                    calEndDate,
                    calDescriptions[i],
                    calLocations[i],
                    calIds[i],
                    gCal_calendarId[i],
                    nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]],
                )
            except:  # subscribe calendar
                print(
                    f"This is a subscribed calendar - {nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]]}"
                )
                create_page(
                    calNames[i],
                    calStartDate,
                    calEndDate,
                    calDescriptions[i],
                    calLocations[i],
                    calIds[i],
                    gCal_calendarId[i],
                    nt.GCAL_DIC_KEY_TO_VALUE[gCal_calendarId[i]],
                )

    print("\n")


####################################################
########   Google deleted items by Notion   #######
####################################################
def deleteEvent():
    print("\n")
    print("-------- Deletion | Done? == True in Notion, delete the GCal event --------")
    resultList = queryNotionEvent_delete()

    print(resultList)
    if len(resultList) > 0:
        for i, el in enumerate(resultList):
            # make sure that"s what you want
            summary = el["properties"]["Task Name"]["title"][0]["text"]["content"]
            pageId = el["id"]
            calendarID = nt.GCAL_DIC[
                el["properties"][nt.CALENDAR_NOTION_NAME]["select"]["name"]
            ]
            try:
                eventId = el["properties"][nt.GCALEVENTID_NOTION_NAME]["rich_text"][0][
                    "text"
                ]["content"]
            except Exception as e:
                print(
                    f"{summary} does not have event ID. Make sure that it exists in Notion"
                )
                print(e)
                sys.exit()
            print(f"{i}th processing GCal Event {summary}, EventID {eventId}")

            try:  # delete Gcal event
                GOOGLE_SERVICE.service.events().delete(
                    calendarId=calendarID, eventId=eventId
                ).execute()
                print(f"{i}th Deleting GCal Event {summary}, EventID {eventId}")
            except:
                continue

            # delete google event id and Cal id in Notion
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
                print(json.dumps(el, indent=4, sort_keys=True))
                print("\n")


def gcal_event_sample(name=nt.GCAL_DEFAULT_NAME, num=1):
    calendarID = ""  # input manually
    eventID = ""  # input manually
    events = GOOGLE_SERVICE.service.events().list(calendarId=calendarID).execute()
    if eventID != "":
        for i, el in enumerate(events["items"]):
            if el["id"] == eventID:
                print(f"Find {eventID}")
                print(events["items"][i]["location"])
                break
    else:
        print(events["items"][num])
