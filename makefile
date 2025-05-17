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
	read -p "Use token **template**? (yes/no): " use_template; \
	if [ "$$use_template" = "yes" ]; then \
		TOKEN_DIR="token_template"; \
	else \
		read -p "Type the real token folder name to confirm (e.g., token): " folder_confirm; \
		if [ "$$folder_confirm" != "token" ]; then \
			echo "❌ Folder confirmation failed. Aborting."; \
			exit 1; \
		fi; \
		TOKEN_DIR="$$folder_confirm"; \
	fi; \
	if [ ! -f "$${TOKEN_DIR}/token.json" ] || [ ! -f "$${TOKEN_DIR}/notion_setting.json" ]; then \
		echo "❌ Required files not found in $$TOKEN_DIR. Aborting."; \
		exit 1; \
	fi; \
	S3_GOOGLE_PATH=$${uuid}/token/google; \
	S3_NOTION_PATH=$${uuid}/token/notion; \
	echo ""; \
	echo "📦 Will upload the following files:"; \
	echo " - $${TOKEN_DIR}/token.json           → s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_PATH}/"; \
	echo " - $${TOKEN_DIR}/notion_setting.json  → s3://$(S3_BUCKET_NAME)/$${S3_NOTION_PATH}/"; \
	echo ""; \
	if [ "$(DRY_RUN)" = "true" ]; then \
		echo "🧪 DRY RUN MODE: Skipping actual upload."; \
	else \
		read -p "❓ Are you sure you want to upload these tokens? (yes/no): " confirm; \
		if [ "$$confirm" = "yes" ]; then \
			echo "⏫ Uploading to S3..."; \
			aws s3 cp $${TOKEN_DIR}/notion_setting.json s3://$(S3_BUCKET_NAME)/$${S3_NOTION_PATH}/; \
			aws s3 cp $${TOKEN_DIR}/token.json s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_PATH}/; \
			echo "✅ Upload complete for UUID: $$uuid"; \
		else \
			echo "❌ Upload canceled."; \
		fi; \
	fi


# list S3 bucket and token paths
list-s3-bucket:
	@read -p "Enter your UUID: " uuid; \
	S3_GOOGLE_PATH=$${uuid}/token/google; \
	S3_NOTION_PATH=$${uuid}/token/notion; \
	echo "🔍 Checking S3 root..."; \
	aws s3 ls s3://$(S3_BUCKET_NAME); \
	echo ""; \
	echo "🔍 Checking Notion token path..."; \
	aws s3 ls s3://$(S3_BUCKET_NAME)/$${S3_NOTION_PATH}/; \
	echo ""; \
	echo "🔍 Checking Google token path..."; \
	aws s3 ls s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_PATH}/; \
	echo ""; \
	read -p "👀 Do you want to preview the token content? (yes/no): " preview; \
	if [ "$$preview" = "yes" ]; then \
		if ! command -v jq >/dev/null 2>&1; then \
			echo "⚠️ 'jq' is not installed. Install it to pretty-print JSON."; \
		else \
			echo "📄 Notion token (pretty JSON):"; \
			aws s3 cp s3://$(S3_BUCKET_NAME)/$${S3_NOTION_PATH}/notion_setting.json - | jq .; \
			echo ""; \
			echo "📄 Google token (pretty JSON):"; \
			aws s3 cp s3://$(S3_BUCKET_NAME)/$${S3_GOOGLE_PATH}/token.json - | jq .; \
		fi \
	else \
		echo "🔒 Skipped token preview for privacy."; \
	fi



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
