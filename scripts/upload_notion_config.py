import boto3
import time
from boto3.dynamodb.types import TypeSerializer

# -------------------------
# CONFIG
# -------------------------
UUID = ""
TABLE_NAME = ""
FIELD_NAME = ""

payload = {
    "goback_days": 1,
    "goforward_days": 2,
    "database_id": "xxxxxxx",
    "timecode": "+08:00",
    "timezone": "Asia/Taipei",
    "default_event_length": 60,
    "default_start_time": 8,
    "gcal_dic": [
        {
            "Calendar_Name1": "xxxxxx@gmail.com"
        }
    ],
    "page_property": [
        {
            "Task_Notion_Name": "Task Name",
            "Date_Notion_Name": "Date",
            "Initiative_Notion_Name": "Initiative",
            "Status_Notion_Name": "Status",
            "Location_Notion_Name": "Location",
            "ExtraInfo_Notion_Name": "Extra Info",
            "GCal_Name_Notion_Name": "Calendar",
            "GCal_EventId_Notion_Name": "GCal Event Id",
            "GCal_Sync_Time_Notion_Name": "GCal Sync Time",
            "GCal_End_Date_Notion_Name": "GCal End Date",
            "Delete_Notion_Name": "GCal Deleted?",
            "CompleteIcon_Notion_Name": "GCal Icon"
        }
    ]
}

# -------------------------
# Convert Python dict → DynamoDB JSON
# -------------------------
serializer = TypeSerializer()
ddb_payload = serializer.serialize(payload)["M"]

# -------------------------
# DynamoDB Client
# -------------------------
client = boto3.client("dynamodb")  # uses AWS CLI local credentials

def update_notion_config():
    response = client.update_item(
        TableName=TABLE_NAME,
        Key={"uuid": {"S": UUID}},
        UpdateExpression=f"SET {FIELD_NAME} = :cfg, updatedAt = :now",
        ExpressionAttributeValues={
            ":cfg": {"M": ddb_payload},
            ":now": {"N": str(int(time.time() * 1000))}
        },
        ReturnValues="UPDATED_NEW"
    )

    print("Update complete:")
    print(response)


if __name__ == "__main__":
    update_notion_config()
