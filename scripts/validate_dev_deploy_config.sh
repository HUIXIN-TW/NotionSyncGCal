#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

require_env() {
  local runtime_name="$1"
  local source_name="$2"

  if [[ -z "${!runtime_name:-}" ]]; then
    fail "$source_name is required."
  fi
}

require_env AWS_REGION DEV_AWS_REGION
require_env ECR_ACCOUNT_ID DEV_ECR_ACCOUNT_ID
require_env IMAGE_NAME DEV_ECR_REPOSITORY
require_env FUNCTION_NAME DEV_LAMBDA_FUNCTION_NAME

if [[ ! "$AWS_REGION" =~ ^[a-z]{2}(-[a-z0-9]+)+-[0-9]+$ ]]; then
  fail "DEV_AWS_REGION has an invalid format."
fi

if [[ ! "$ECR_ACCOUNT_ID" =~ ^[0-9]{12}$ ]]; then
  fail "DEV_ECR_ACCOUNT_ID must be exactly 12 digits."
fi

if (( ${#IMAGE_NAME} > 256 )) || [[ ! "$IMAGE_NAME" =~ ^[a-z0-9]+([._/-][a-z0-9]+)*$ ]]; then
  fail "DEV_ECR_REPOSITORY has an invalid format."
fi

if (( ${#FUNCTION_NAME} > 64 )) || [[ ! "$FUNCTION_NAME" =~ ^[A-Za-z0-9_-]+$ ]]; then
  fail "DEV_LAMBDA_FUNCTION_NAME has an invalid format."
fi

echo "Dev deployment configuration validation passed."
