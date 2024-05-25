## How to install the app

- Step1: Fork or Clone git repository

  For beginners, you can download this repository directly.

  1. Click the green `Code` button on the top-right corner of the page, and then click `Download ZIP`

     <img src="./assets/download.png" width="600" height="auto">

     You can unzip it and then change the folder name to whatever you want. Have a look these files and folders. We will change some of them later.

     <img src="./assets/folder.png" width="600" height="auto">

  For advanced users, you can fork this repository and then clone it.

  1. In the top-right corner of the page, click Fork.

    <img src="./assets/fork.png" width="600" height="auto">

  2. Select an owner for the forked repository.

  3. Choose the main branch

  4. Click `Create Fork`.

  5. Clone your forked repository

    <img src="./assets/code.png" width="600" height="auto">

  6. Open the terminal, and type:

  ```bash
  git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY-NAME
  ```

  7. Change directory to where you download, and then install packages

  ```bash
  cd YOUR-REPOSITORY-NAME
  pip3 install -r requirements.txt
  ```

  If you update the requirements.txt, you can use the following commend to update it.

  ```bash
  pip3 freeze > requirements.txt
  ```

- Step2: Duplicate the Notion template as the initial database [NotionGCal](https://huixin.notion.site/aa639e48cfee4216976756f33cf57c8e?v=6db9353f3bc54029807c539ffc3dfdb4)
  If you are familar with the entire code, you are welcome to customise your own template. However, I recommend you to use my template and do not change the property names at the first time.

- Step3: Notion Connection Setting

  1. Visit Notion Developer website

  - Directly click [Notion Developer](https://www.notion.so/my-integrations), and make sure you are logged in, or
  - Via Notion App, open your Notion and click `Settings and members`, and then click here
    <img src="./assets/connection.png" width="600" height="auto">

  2. Create `New integration` and then `Submit`

     <img src="./assets/newintegration.png" width="600" height="auto">

  3. Open the template page, click `...`, then click `Add connection`. (Select what you name your connection)

     <img src="./assets/notionconnect.png" width="600" height="auto">

- Step4: Complete the `notion_setting.json` in the `token_blank` folder, and then rename the folder `token_blank` with `token` (.gitignore will exclude files in this `token` folder to protect your sensitive information when you push your code to github. If you don't want to use github, you can still need to rename the folder but can ignore the reason why we do this)

  - "notion_token": "Paste your Internal Integration Token which starts with `secret*...`",
    <img src="./assets/secrets.png" width="600" height="auto">

  - "urlroot": "https://www.notion.so/{YOURNOTIONNAME}/{databaseID}?XXXXX",
    <img src="./assets/copylink.png" width="600" height="auto">

  - the following items is up to you. If you are the first time using terminal or python, I recommend you to use 1 or 2 fir "goforward_days". This mean that the code will synchromise the events from 1 day before to 2 days after today. If you are familar with python, you can change them as you want.

    - "timecode": "+08:00",
    - "timezone": "Asia/Taipei",
    - "goback_days": 1,
    - "goforward_days": 2,
    - "delete_option": 0,
    - "event_length": 60,
    - "start_time": 8,
    - "allday_option": 0,

  - Go to your google calendar page, and then click `Settings` on the top-right, next, scroll the left bar to find `Setting for my calendar`. Click it, calendar `Name` is on the top, and scroll down to find `Calendar ID`

  - Enter your default calendar at least. If you want to add multiple calendars, separate them by `,`

    - "gcal_dic": [{"YOUR CALENDAR NAME1": "YOUR CALENDAR ID1", "YOUR CALENDAR NAME2": "YOUR CALENDAR ID2"}],

    If you set up multiple calendars, it will look like this:
    <img src="./assets/multiplecal.png" width="600" height="auto">

  - The following items are column names in notion based on my template. The `page_property` section is setting these column name.

    - "Task_Notion_Name": "Task Name",
    - "Date_Notion_Name": "Date",
    - "Initiative_Notion_Name": "Initiative",
    - "ExtraInfo_Notion_Name": "Extra Info",
    - "Location_Notion_Name": "Location",
    - "On_GCal_Notion_Name": "On GCal?",
    - "NeedGCalUpdate_Notion_Name": "NeedGCalUpdate",
    - "GCalEventId_Notion_Name": "GCal Event Id",
    - "LastUpdatedTime_Notion_Name" : "Last Updated Time",
    - "Calendar_Notion_Name": "Calendar",
    - "Current_Calendar_Id_Notion_Name": "Current Calendar Id",
    - "Delete_Notion_Name": "Done?",
    - "Status_Notion_Name": "Status",
    - "Page_ID_Notion_Name": "PageID",
    - "CompleteIcon_Notion_Name": "CompleteIcon"
      You can change the column name without modifying the main code zone as long as you alter this section and notion columns consistently.

- Step5: Create a google token, and make sure your scope include google calendar

  1. Go to [google developers](https://console.developers.google.com/)

  2. Create a New Project, and select it

     <img src="./assets/library.png" width="600" height="auto">
     <img src="./assets/newproject.png" width="600" height="auto">
     <img src="./assets/selectproject.png" width="600" height="auto">

  3. Clikc `+ ENABLE APIS AND SERVICES` to enable google calendar API, and then add your email

     <img src="./assets/library.png" width="600" height="auto">
     <img src="./assets/searchapi.png" width="600" height="auto">

  4. You enabled google calendar API successfully if you see this

     <img src="./assets/enabled.png" width="600" height="auto">

  5. Click `+ CREATE CREDENTIALS`

     <img src="./assets/OAuthID.png" width="600" height="auto">

  6. Click `CONFIGURE CONSENT SCREEN`, and then select `External` and click `CREATE`

  7. Name whatever you want, and select your email as `User support email`. Next, type your email to `Developer contact information`, and then click `SAVE & CONTINUE`

  8. Click `ADD OR REMOVE SCOPES`, and then Select the scope as belows. Scroll down and click `UPDATE`

     <img src="./assets/addscope.png" width="600" height="auto">
     <img src="./assets/searchscope.png" width="600" height="auto">
     <img src="./assets/googleapi.png" width="600" height="auto">

  9. Scroll down, and click `Save and Continue`

  10. Click `+ ADD USERS` and click `Save and Continue`

      <img src="./assets/adduser.png" width="600" height="auto">

  11. Create the OAuth client ID

      <img src="./assets/createcredential.png" width="600" height="auto">

  12. Name your application, and then click `CREATE`

      <img src="./assets/credentialname.png" width="600" height="auto">

  13. Download `.json` (Note: Dont show with others otherwise they may access your account)

      <img src="./assets/credentialdownload.png" width="600" height="auto">

  14. Rename `client_secret_XXXXXXXXXXXX.json` to `client_secret.json`, and then move it into `token` folder

- Step6: Download [python](https://www.python.org/downloads/) (or skip this step if you use Docker)

  1. Visit the official Python website at https://www.python.org/downloads/.

  2. On the Downloads page, you will see the latest version of Python available for download. The website will automatically detect your operating system and suggest the appropriate version for your platform (Windows, macOS, or Linux). If you want to download a different version, click on the "Looking for a specific release?" link.

  3. Click on the download link for the version of Python you want to install. You will typically have two options: one for the latest stable release (e.g., Python 3.x.x) and one for the latest legacy release (e.g., Python 2.7.x). It is recommended to choose the latest stable release unless you have specific requirements for using Python 2.

  4. After clicking the download link, you will be redirected to the download page. Scroll down to find the files for your operating system. Choose the installer appropriate for your system architecture (32-bit or 64-bit).

  5. Once the installer is downloaded, run the installer executable (.exe file on Windows or .pkg file on macOS) by double-clicking on it.

  6. Follow the installation instructions provided by the installer. You can usually accept the default settings unless you have specific requirements. Make sure to check the box that says "Add Python to PATH" during the installation process, as this will make it easier to use Python from the command line.

  7. After the installation is complete, open a new command prompt (Windows) or terminal (macOS/Linux)

  <img src="./assets/terminal.png" width="600" height="auto">

  8. type python --version to verify that Python is installed correctly. You should see the version number of Python displayed.

  <img src="./assets/pythonversion.png" width="600" height="auto">

  9. Install python packages

  ```bash
  pip3 install -r requirements.txt
  ```

  There are a lot of videos on youtube to teach you how to install python. I recommend you to watch them if you are not familar with python.

- Step7: If you are familar with Docker, you can use Docker instaed of python to run this code.

  - Warning: if you use docker, change "docker": true, in `notion_setting.json`. Otherwise, the creds will not work when you activated it at the first time.

  1. download [Docker](https://www.docker.com/products/docker-desktop).

  2. open the terminal and type:

  ```bash
  docker build -t sync .
  ```

  3. Third, type to run default script:

  ```bash
  docker run -it sync
  ```

  or add the following commend to update from google calendar time only. You can check the commend in `main.py` or the following Sychronise Notion with Google Calendar section.

  ```bash
  docker run -it sync src/main.py -gt
  ```

  - At the first time, you need to copy the creds from brower to terminal. And copy the code and paste it into the `token.pkl` in token folder. Run the above code again, and then you can use docker to run the code.

  - clear all Docker containers after you finish it.

  ```bash
  docker rm $(docker ps -aq)
  ```

  4. Other commend to check the container. You can start the docker container and then run the code in the container.

  ```bash
  docker ps -a
  ```

  ```bash
  docker start <CONTAINER ID>
  ```

  ```bash
  docker exec -it <CONTAINER ID> sh
  ```

  You are in docker container

  ```docker
  # python src/main.py
  ```

  Exit docker container

  ```docker
  exit
  ```

  Stop docker container

  ```docker
  docker stop <CONTAINER ID>
  ```

  Clear all Docker containers

  ```docker
  docker rm $(docker ps -aq)
  ```

Congraduations! All settings are done! Let's run the program.