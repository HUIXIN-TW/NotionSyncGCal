import notion_token 
import gcal_token 
from datetime import datetime, timedelta


#TODO: All function have not been tested yet

nt = notion_token.Notion()
gt = gcal_token.Google()


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
        x = gt.service.events().insert(calendarId=newCalId, body=event).execute()
    else:
        if newCalId == oldCalId:
            x = (
                gt.service.events()
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
                gt.service.events()
                .move(calendarId=oldCalId, eventId=exist_eventId, destination=newCalId)
                .execute()
            )
            # update
            x = (
                gt.service.events()
                .update(calendarId=newCalId, eventId=exist_eventId, body=event)
                .execute()
            )
    return x["id"]


# METHOD TO MAKE A EVENT ID LIST


def queryGCalId(id, num=300):
    x = (
        gt.service.events()
        .list(
            calendarId=id,
            maxResults=num,
            timeMin=nt.GOOGLE_TIMEMIN,
            timeMax=nt.GOOGLE_TIMEMAX,
        )
        .execute()
    )
    return x


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
                gt.service.events().delete(
                    calendarId=calendarID, eventId=eventId
                ).execute()
                print(f"{i}th Deleting GCal Event {summary}, EventID {eventId}")
            except:
                continue

            # delete google event id and Cal id in Notion
            deleteGInfo(pageId)
    else:
        print("---------------------- No deleted the GCal event ----------------------")
