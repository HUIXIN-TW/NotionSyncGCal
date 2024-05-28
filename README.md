# Notion Task Synchronise with Google Calendar Event

> command-line interface to sync data between Notion Task and Google Calendar Event.

Do you find yourself juggling between Notion and Google Calendar to manage your events? Fret not! This awesome code is here to save your day. It magically extracts event details from your Notion Database and seamlessly integrates them into your Google Calendar events. There's more! It even adds a handy URL to your GCal event, so you can effortlessly jump back to the specific Notion Page related to the event. How cool is that?

**Warning**: Proceed with caution! This repo wields the power to make changes to your Notion database and Google Calendar. So, if you're not confident about what you're doing, buckle up and brace yourself for some unexpected surprises.

## What you will need to get started

- Google account
- Notion account
- GitHub account (optional)
- python3

## Current Capabilities:

- update from google cal to notion task
- update from notion task to google cal

### Functions:

- Ability to change timezones by changing `timecode` and `timezone` in `notion_setting`
- Ability to change the date range by changing `goback_days` and `goforward_days` in `notion_setting.json` (If you are new here, please use 1 and 2 days respectively before you understand the code)
- Able to decide the default length of new GCal events by changing `default_event_length` in `notion_setting.json`
- Option to delete gCal events if checked off as `GCal Deleted?` column in Notion
- Sync across _multiple calendars_ and choose which calendar you would like to sync by changing `gcal_dic` in `notion_setting.json`
- Able to name the required Notion columns whatever you want and have the code work by changing `page_property` in `notion_setting.json`
- credential and OAuth consent screen with google calendar scope

# Sychronise Notion with Google Calendar

Go to the terminal, and change the folder to where these script are:

```bash
cd src
```

## Basic Synchronization

To run the basic synchronization between Notion and Google Calendar:

```bash
python3 main.py
```

## Synchronization with Specific Date Range

To synchronize events based on a specific date range, use the following command:

```bash
python3 main.py -t <look_back_days> <look_ahead_days>
```

`<look_back_days>`: Number of days to look back from the current date.

`<look_ahead_days>`: Number of days to look forward from the current date.

## Force Sync Options

### Sync from Google Calendar to Notion

To force an update of Notion tasks from Google Calendar events within a specified date range, use the following command:

```bash
python3 main.py -g <look_back_days> <look_ahead_days>
```

### Sync from Notion to Google Calendar

To force an update of Google Calendar events from Notion tasks within a specified date range, use the following command:

```bash
python3 main.py -n <look_back_days> <look_ahead_days>
```

## Test

Change the folder to where these script are:

```bash
cd tests
```
