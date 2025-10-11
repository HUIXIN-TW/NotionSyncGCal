import boto3
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

table_name = os.getenv("DYNAMODB_USER_TABLE", "")
if not table_name:
    raise ValueError("DYNAMODB_USER_TABLE environment variable is not set.")
print(f"Table name: {table_name}")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(table_name)

response = table.scan()
items = response.get("Items", [])

for item in items:
    print(f"{item.get('uuid')} -> {item.get('email')}")
