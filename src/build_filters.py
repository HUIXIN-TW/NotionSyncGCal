def build_date_range_filter(property_name, before_date, after_date):
    """Build a filter for date range."""
    return {
        "and": [
            {"property": property_name, "date": {"on_or_before": before_date}},
            {"property": property_name, "date": {"on_or_after": after_date}},
        ]
    }


def build_checkbox_filter(property_name, value):
    """Build a filter for checkbox properties."""
    return {"property": property_name, "checkbox": {"equals": value}}


def build_formula_checkbox_filter(property_name, value):
    """Build a filter for checkbox properties."""
    return {"property": property_name, "formula": {"checkbox": {"equals": True}}}


def build_or_filter(filters):
    """Build an OR filter."""
    return {"or": filters}


def build_and_filter(filters):
    """Build an AND filter."""
    return {"and": filters}


def build_string_equality_filter_for_formula(property_name, value):
    """Helper function to build a Notion filter to match a string equality condition in a formula property."""
    return {"property": property_name, "formula": {"string": {"equals": value}}}


def build_properties_update(properties_dict):
    """Helper function to build properties update dictionary."""
    return {"properties": properties_dict}


def build_update_page_time_properties(
    calname, calstartdate, calenddate, calid, gCal_id, gCal_name
):
    """Helper function to build properties for updating a page."""
    properties = {
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
    }
    return build_properties_update(properties)


def build_create_or_update_page_properties(
    calname,
    calstartdate,
    calenddate,
    caldescription,
    callocation,
    calid,
    gCal_id,
    gCal_name,
    is_create=True,
):
    """Helper function to build properties for creating or updating a page."""
    properties = {
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
    }
    if is_create:
        properties[nt.ON_GCAL_NOTION_NAME]["checkbox"] = True
    return build_properties_update(properties)
