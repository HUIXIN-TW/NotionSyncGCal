import boto3
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

if len(sys.argv) != 2:
    print("Usage: python upload_tokens.py <uuid>")
    sys.exit(1)

uuid = sys.argv[1]
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
S3_GOOGLE_KEY = os.getenv("S3_GOOGLE_KEY", "")
S3_NOTION_KEY = os.getenv("S3_NOTION_KEY", "")
print(f"S3_BUCKET_NAME: {S3_BUCKET_NAME}")
print(f"S3_GOOGLE_KEY: {S3_GOOGLE_KEY}")
print(f"S3_NOTION_KEY: {S3_NOTION_KEY}")
if not S3_BUCKET_NAME or not S3_GOOGLE_KEY or not S3_NOTION_KEY:
    raise ValueError("Environment variable is not set.")

s3 = boto3.client("s3")


def upload(local_path, bucket, s3_key):
    print(f"Uploading {local_path} to s3://{bucket}/{s3_key}")
    s3.upload_file(local_path, bucket, s3_key)


upload("token_template/notion_setting.json", S3_BUCKET_NAME, f"{uuid}/{S3_NOTION_KEY}")
upload("token_template/token.json", S3_BUCKET_NAME, f"{uuid}/{S3_GOOGLE_KEY}")
