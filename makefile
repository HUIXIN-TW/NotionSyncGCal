# Variables
AWS_PROFILE := huixin
LAMBDA_LAYER_NAME := NotionSyncDeps

# Check if environment variables are set
check-env:
	@echo "S3_BUCKET_NAME=$(S3_BUCKET_NAME)"
	@echo "S3_NOTION_TOKEN_FOLDER=$(S3_NOTION_TOKEN_FOLDER)"
	@echo "S3_GOOGLE_TOKEN_FOLDER=$(S3_GOOGLE_TOKEN_FOLDER)"

# Lint: Run Prettier and Black
lint:
	prettier --write .
	black src/ lambda_function.py --line-length 120
	flake8 src/ lambda_function.py --max-line-length 120

# Upload token files to S3
upload-app-token-s3:
	aws s3 cp token/client_secret.json s3://$(S3_BUCKET_NAME)/
	echo "client_secret.json uploaded to S3 bucket $(S3_BUCKET_NAME)"

# Upload token files to S3
upload-user-token-s3:
	aws s3 cp token/notion_setting.json s3://$(S3_BUCKET_NAME)/$(S3_NOTION_TOKEN_FOLDER)/
	aws s3 cp token/token.pkl s3://$(S3_BUCKET_NAME)/$(S3_GOOGLE_TOKEN_FOLDER)/
	echo "token.pkl and notion_setting.json uploaded to S3 bucket $(S3_BUCKET_NAME)/$(S3_NOTION_TOKEN_FOLDER)"


# Check S3 bucket and token paths
check-s3-bucket:
	@echo "🔍 Checking S3 root..."
	aws s3 ls s3://$(S3_BUCKET_NAME)

	@echo "🔍 Checking Notion token path..."
	aws s3 ls s3://$(S3_BUCKET_NAME)/$(S3_NOTION_TOKEN_FOLDER)/

	@echo "🔍 Checking Google token path..."
	aws s3 ls s3://$(S3_BUCKET_NAME)/$(S3_GOOGLE_TOKEN_FOLDER)/


# Open AWS Profile (shortcut)
open-aws-profile:
	bat ~/.aws/config

# Edit AWS Profile (shortcut)
edit-aws-profile:
	aws configure --profile $(AWS_PROFILE)

# Zip Lambda Layer and Upload to Lambda
upload-lambda-layer:
	rm -rf lambda_layer
	mkdir -p lambda_layer/python
	pip install -r requirements.txt --target lambda_layer/python
	pip uninstall boto3 -y
	cd lambda_layer && zip -r9 ../lambda_layer.zip python
	aws lambda publish-layer-version \
		--layer-name $(LAMBDA_LAYER_NAME) \
		--description "Dependencies for Notion/Google Calendar Sync" \
		--zip-file fileb://lambda_layer.zip \
		--compatible-runtimes python3.12

release-zip-v2.0.0:
	rm -rf dist
	mkdir dist
	cp -r src lambda_function.py requirements.txt dist/
	cd dist
	zip -r NotionSyncGCal-v2.0.0.zip .

# Help: Display available commands
help:
	@echo "Available commands:"
	@echo "  lint                Run Prettier and Black"
	@echo "  upload-app-token-s3 Upload client_secret.json to S3"
	@echo "  upload-user-token-s3 Upload token.pkl and notion_setting.json to S3"
	@echo "  open-aws-profile    Open AWS profile configuration"
	@echo "  edit-aws-profile    Edit AWS profile configuration"
	@echo "  upload-lambda-layer  Zip Lambda Layer and upload to Lambda"
	@echo "  release-zip-v2.0.0   Create a zip file for release v2.0.0"
	@echo "  help                Display this help message"
