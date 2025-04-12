# Variables
AWS_PROFILE := huixin
LAMBDA_LAYER_NAME := NotionSyncDeps

# Lint: Run Prettier and Black
lint:
	prettier --write .
	black .

# Upload token files to S3
upload-s3:
	aws s3 cp token/notion_setting.json s3://$(S3_BUCKET_NAME)/$(S3_TOKEN_FOLDER)/
	aws s3 cp token/client_secret.json s3://$(S3_BUCKET_NAME)/$(S3_TOKEN_FOLDER)/
	aws s3 cp token/token.pkl s3://$(S3_BUCKET_NAME)/$(S3_TOKEN_FOLDER)/

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

# Help: Display available commands
help:
	@echo "Available commands:"
	@echo "  lint                   Run Prettier and Black for linting"
	@echo "  upload-s3              Upload token files to S3"
	@echo "  open-aws-profile       Open AWS profile configuration"
	@echo "  upload-lambda-layer    Zip the Lambda layer and upload it to AWS"
