# Notion Synchronise with Google Calendar
The code will extract the event name, date/time, a category, and text from the Notion Dashboard and integrate that information into your GCal event. Additionally, it will also add a URL source code the GCal event so you can click on the URL and automatically be brought over to the specific Notion Page that your event is at.

WARNING: This repo will access Notion's database and Google Calendar if you do not know what are you doing, it may cause unwanted changes.

## Current Capabilities:
- update events from google cal to notion
- update events from notion to google cal

### Functions:
- Sync across *multiple calendars* and choose which calendar you would like to sync
- Able to name the required Notion columns whatever you want and have the code work
- Able to add in end times and sync that across both platforms
- Able to decide if a date in Notion will make an event at a desired time or if it will make an All-day event
- Ability to change timezones
- Option to delete gCal events if checked off as `Done?` in Notion
- Able to decide default length of new GCal events 
    - credential and OAuth consent screen with google calendar scope

Inspired by [akarri2001/Notion-and-Google-Calendar-2-Way-Sync](https://github.com/akarri2001/Notion-and-Google-Calendar-2-Way-Sync)

## How to install it
- Download or Fork

    1. In the top-right corner of the page, click Fork.

    ![fork](./assets/fork.png)

    2. Select an owner for the forked repository.

    3. Choose the main branch 

    4. Click Create fork.

    5. Cloning your forked repository

    ![code](./assets/code.png)

    6. Open terminal

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY-NAME
```

- `cd FILELOCTION`, and then install packages

```bash
pip3 install -r requirements.txt
```

- Notion Connect Setting (pending)

- Download the template as the initial database

[NotionGCal](https://huixin.notion.site/aa639e48cfee4216976756f33cf57c8e?v=6db9353f3bc54029807c539ffc3dfdb4)

- Complete the notion_setting.json
    - then change `token_blank` into `token`

- Create a google token, and make sure your scope include google calendar (pending)
    1. Go to https://console.developers.google.com/ 
    2. Create a New Project

- Update from notion to google

```bash
python3 main.py
```

- Update from google time which is in Notion, and create google new events which is not in Notion

```bash
python main.py -gt
```

- Create google new events only

```bash
python main.py -gc
```

- Replace all content of google event
(I don't recommend this function since most content is made by Notion tasks.)

```bash
python main.py -ga
```

- Delete google events which is ticked in Notion

```bash
python main.py -r
```