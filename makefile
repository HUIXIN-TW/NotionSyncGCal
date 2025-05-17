# Variables
AWS_PROFILE := huixin
LAMBDA_LAYER_NAME := NotionSyncDeps


# Lint: Run Prettier and Black
lint:
	prettier --write .
	black src/ lambda_function.py --line-length 120
	flake8 src/ lambda_function.py --max-line-length 120


# Upload app token to S3
upload-app-token-s3:
	@echo ""
	@echo "📦 You are about to upload:"
	@echo " - token/client_secret.json → s3://$(S3_BUCKET_NAME)/"
	@echo ""
	@read -p "❓ Proceed with upload? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "⏫ Uploading..."; \
		aws s3 cp token/client_secret.json s3://$(S3_BUCKET_NAME)/; \
		echo "✅ Upload complete."; \
	else \
		echo "❌ Upload canceled."; \
	fi


# Upload token files to S3
upload-user-token-s3:
	@read -p "Enter your UUID (USERNAME): " uuid; \
	S3_GOOGLE_PATH=$${uuid}/token/google; \
	S3_NOTION_PATH=$${uuid}/token/notion; \
	echo "📦 Will upload the following files:"; \
	echo " - token/token.json → s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_PATH}/"; \
	echo " - token/notion_setting.json → s3://$(S3_BUCKET_NAME)/$${S3_NOTION_PATH}/"; \
	echo ""; \
	read -p "❓ Are you sure you want to upload these tokens? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		echo "⏫ Uploading to S3..."; \
		aws s3 cp token/notion_setting.json s3://$(S3_BUCKET_NAME)/$${S3_NOTION_PATH}/; \
		aws s3 cp token/token.json s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_PATH}/; \
		echo "✅ Upload complete for UUID: $$uuid"; \
	else \
		echo "❌ Upload canceled."; \
	fi


# list S3 bucket and token paths
list-s3-bucket:
	@read -p "Enter your UUID: " uuid; \
	S3_NOTION_TOKEN_FOLDER=$${uuid}/token/notion; \
	S3_GOOGLE_TOKEN_FOLDER=$${uuid}/token/google; \
	echo "🔍 Checking S3 root..."; \
	aws s3 ls s3://$(S3_BUCKET_NAME); \
	echo "🔍 Checking Notion token path..."; \
	aws s3 ls s3://$(S3_BUCKET_NAME)/$${S3_NOTION_TOKEN_FOLDER}/ || echo "❌ Notion token path not found."; \
	echo "🔍 Checking Google token path..."; \
	aws s3 ls s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_TOKEN_FOLDER}/ || echo "❌ Google token path not found."


# Open AWS Profile (shortcut)
open-aws-profile:
	@echo "AWS Profile: $(AWS_PROFILE)"
	@aws configure list --profile $(AWS_PROFILE)
	@echo "\nCredentials File:"
	@cat ~/.aws/credentials | grep -A 3 "\[${AWS_PROFILE}\]"
	@echo "\nConfig File:"
	@cat ~/.aws/config | grep -A 3 "\[profile ${AWS_PROFILE}\]"


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

# Create release zip
release-zip:
	rm -rf dist
	mkdir dist
	cp -r src lambda_function.py requirements.txt dist/
	cd dist
	zip -r NotionSyncGCal-v2.0.0.zip .
