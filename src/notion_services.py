from datetime import datetime, timedelta
import logging
import notion_token

from build_filters import (
    build_date_range_filter,
    build_checkbox_filter,
    build_formula_checkbox_filter,
    build_or_filter,
    build_and_filter,
    build_string_equality_filter_for_formula,
    build_properties_update,
    build_create_or_update_page_properties,
)


# Initialize the Notion token
nt = notion_token.Notion()

# Configure logging
logging.basicConfig(filename="notion_services.log", level=logging.INFO)


def format_date(date_obj):
    """Helper function to format dates."""
    try:
        formatted_date = date_obj.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception as e:
        logging.error(f"Error formatting date: {e}")
        formatted_date = None
    return formatted_date


def parse_date(date_str):
    """Helper function to parse dates"""
    try:
        parsed_date = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception as e:
        logging.error(f"Error parsing date: {e}")
        parsed_date = None
    return parsed_date


def notion_query(database_id, filters):
    """Helper function to query the Notion database"""
    try:
        return nt.NOTION.databases.query(database_id=database_id, filter=filters)
    except Exception as e:
        logging.error(f"Error querying Notion database: {e}")
        return None


def notion_update(page_id, properties):
    """Helper function to update a page in the Notion database"""
    try:
        return nt.NOTION.pages.update(page_id=page_id, properties=properties)
    except Exception as e:
        logging.error(f"Error updating Notion page: {e}")
        return None


def notion_time():
    """Helper function to get the current time in the Notion format"""
    return datetime.now().strftime(f"%Y-%m-%dT%H:%M:%S{nt.TIMECODE}")


def all_notion_eventid(operation_context):
    """Helper function to get all Notion event ids"""
    all_notion_gCal_Ids = []
    all_notion_gCal_Ids_pageid = {}
    resultList = queryNotionEvent_gcal()
    logging.info(f"{operation_context} | Get all Notion event")
    for result in resultList:
        GCalId = result["properties"][nt.GCALEVENTID_NOTION_NAME]["rich_text"][0][
            "text"
        ]["content"]
        all_notion_gCal_Ids.append(GCalId)
        all_notion_gCal_Ids_pageid[GCalId] = result["id"]
    return all_notion_gCal_Ids, all_notion_gCal_Ids_pageid


def queryNotionEvent_all():
    """Helper function to query all Notion events"""
    date_filter = build_date_range_filter(
        nt.DATE_NOTION_NAME, nt.BEFORE_DATE, nt.AFTER_DATE
    )
    delete_filter = build_checkbox_filter(nt.DELETE_NOTION_NAME, False)
    final_filter = build_and_filter([date_filter, delete_filter])
    try:
        my_page = nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID, filter=final_filter
        )
        return my_page["results"]
    except Exception as e:
        logging.error(f"Failed to query Notion database: {e}")
        return []


def queryNotionEvent_notion():
    """Helper function to query Notion events"""
    date_filter = build_date_range_filter(
        nt.DATE_NOTION_NAME, nt.BEFORE_DATE, nt.AFTER_DATE
    )
    delete_filter = build_checkbox_filter(nt.DELETE_NOTION_NAME, False)
    other_filters = [
        build_checkbox_filter(nt.ON_GCAL_NOTION_NAME, False),
        build_formula_checkbox_filter(nt.NEEDGCALUPDATE_NOTION_NAME, True),
    ]
    final_filter = build_and_filter(
        [build_or_filter(other_filters), date_filter, delete_filter]
    )

    try:
        my_page = nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID, filter=final_filter
        )
        return my_page["results"]
    except Exception as e:
        logging.error(f"Failed to query Notion database: {e}")
        return []


def queryNotionEvent_page(id):  # TODO: bug
    """Helper function to query a specific Notion page by ID."""
    page_id_filter = build_string_equality_filter_for_formula(
        nt.PAGE_ID_NOTION_NAME, id
    )
    delete_filter = build_checkbox_filter(nt.DELETE_NOTION_NAME, False)
    final_filter = build_and_filter([page_id_filter, delete_filter])
    try:
        my_page = nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID, filter=final_filter
        )
        results = my_page.get("results", [])
        logging.info(f"Page Query: {results}")
        return results
    except Exception as e:
        logging.error(f"Failed to query Notion page: {e}")
        return []


def queryNotionEvent_gcal():
    """Helper function to query Notion events synced with Google Calendar."""

    on_gcal_filter = build_checkbox_filter(nt.ON_GCAL_NOTION_NAME, True)
    not_deleted_filter = build_checkbox_filter(nt.DELETE_NOTION_NAME, False)
    date_range_filter = build_date_range_filter(
        nt.DATE_NOTION_NAME, nt.BEFORE_DATE, nt.AFTER_DATE
    )

    final_filter = build_and_filter(
        [on_gcal_filter, not_deleted_filter, date_range_filter]
    )

    try:
        my_page = nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID, filter=final_filter
        )
        results = my_page.get("results", [])
        logging.info(f"gCal Query: {results}")
        return results
    except Exception as e:
        logging.error(f"Failed to query Notion gCal events: {e}")
        return []


def queryNotionEvent_delete():
    """Helper function to query deleted Notion events synced with Google Calendar."""

    on_gcal_filter = build_checkbox_filter(nt.ON_GCAL_NOTION_NAME, True)
    is_deleted_filter = build_checkbox_filter(nt.DELETE_NOTION_NAME, True)
    date_range_filter = build_date_range_filter(
        nt.DATE_NOTION_NAME, nt.BEFORE_DATE, nt.AFTER_DATE
    )

    final_filter = build_and_filter(
        [on_gcal_filter, is_deleted_filter, date_range_filter]
    )

    try:
        my_page = nt.NOTION.databases.query(
            database_id=nt.DATABASE_ID, filter=final_filter
        )
        results = my_page.get("results", [])
        logging.info(f"Delete Query: {results}")
        return results
    except Exception as e:
        logging.error(f"Failed to query deleted Notion events: {e}")
        return []


def updateGStatus(page_id):
    """Helper function to update Google status on a Notion page."""
    properties_update = {
        nt.ON_GCAL_NOTION_NAME: {"checkbox": True},
        nt.LASTUPDATEDTIME_NOTION_NAME: {"date": {"start": notion_time(), "end": None}},
    }

    properties_dict = build_properties_update(properties_update)

    try:
        my_page = nt.NOTION.pages.update(page_id=page_id, **properties_dict)
        logging.info(f"Page {page_id} updated successfully.")
        return my_page
    except Exception as e:
        logging.error(f"Failed to update page {page_id}: {e}")
        return None


def updateDefaultCal(page_id, gcal, gcal_id):
    """Helper function to update the default Google Calendar link on a Notion page."""
    properties_update = {
        nt.GCALEVENTID_NOTION_NAME: {"rich_text": [{"text": {"content": gcal}}]},
        nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
            "rich_text": [{"text": {"content": gcal_id}}]
        },
        nt.CALENDAR_NOTION_NAME: {"select": {"name": nt.GCAL_DEFAULT_NAME}},
    }

    properties_dict = build_properties_update(properties_update)

    try:
        my_page = nt.NOTION.pages.update(page_id=page_id, **properties_dict)
        logging.info(f"Page {page_id} updated with default calendar info successfully.")
        return my_page
    except Exception as e:
        logging.error(
            f"Failed to update page {page_id} with default calendar info: {e}"
        )
        return None


def updateCal(page_id, gcal, gcal_id):
    """Helper function to update the Google Calendar link on a Notion page."""
    properties_update = {
        nt.GCALEVENTID_NOTION_NAME: {"rich_text": [{"text": {"content": gcal}}]},
        nt.CURRENT_CALENDAR_ID_NOTION_NAME: {
            "rich_text": [{"text": {"content": gcal_id}}]
        },
    }

    properties_dict = build_properties_update(properties_update)

    try:
        my_page = nt.NOTION.pages.update(page_id=page_id, **properties_dict)
        logging.info(f"Page {page_id} updated with calendar info successfully.")
        return my_page
    except Exception as e:
        logging.error(f"Failed to update page {page_id} with calendar info: {e}")
        return None


def deleteGInfo(page_id):
    """Helper function to delete Google information from a Notion page."""
    clear_property = ""
    properties_update = {
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
    }

    properties_dict = build_properties_update(properties_update)

    try:
        my_page = nt.NOTION.pages.update(page_id=page_id, **properties_dict)
        logging.info(f"Google information deleted from page {page_id} successfully.")
        return my_page
    except Exception as e:
        logging.error(f"Failed to delete Google information from page {page_id}: {e}")
        return None


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
    """Helper function to create a page in Notion."""
    properties = build_create_or_update_page_properties(
        calname,
        calstartdate,
        calenddate,
        caldescription,
        callocation,
        calid,
        gCal_id,
        gCal_name,
    )

    try:
        my_page = nt.NOTION.pages.create(
            parent={"database_id": nt.DATABASE_ID}, properties=properties
        )
        logging.info(f"Added this event to Notion: {calname}")
        logging.info(f"From {calstartdate} to {calenddate}")
        return my_page
    except Exception as e:
        logging.error(f"Failed to create page in Notion: {e}")
        return None


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
    """Helper function to update a page in Notion."""
    properties = build_create_or_update_page_properties(
        calname,
        calstartdate,
        calenddate,
        caldescription,
        callocation,
        calid,
        gCal_id,
        gCal_name,
    )

    try:
        my_page = nt.NOTION.pages.update(page_id=pageid, properties=properties)
        logging.info(f"Updated this event to Notion: {calname}")
        logging.info(f"From {calstartdate} to {calenddate}")
        return my_page
    except Exception as e:
        logging.error(f"Failed to update page in Notion: {e}")
        return None


def update_page_time(
    pageid,
    calname,
    calstartdate,
    calenddate,
    calid,
    gCal_id,
    gCal_name,
):
    """Helper function to update a page in Notion."""
    properties = build_update_page_time_properties(
        calname, calstartdate, calenddate, calid, gCal_id, gCal_name
    )

    try:
        my_page = nt.NOTION.pages.update(page_id=pageid, properties=properties)
        logging.info(f"Updated this event to Notion: {calname}")
        logging.info(f"From {calstartdate} to {calenddate}")
        return my_page
    except Exception as e:
        logging.error(f"Failed to update page in Notion: {e}")
        return None
