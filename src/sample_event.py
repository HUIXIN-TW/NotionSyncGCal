import notion_token

# Initialize the Notion token
nt = notion_token.Notion()

# TODO: Havent TEST yet
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
