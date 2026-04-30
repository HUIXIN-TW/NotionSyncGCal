#!/usr/bin/env bash
# Local developer runner for APP_MODE=cloud and APP_MODE=local.
#
# SECURITY CONTRACT:
#   - Never prints AWS, Notion, Google, or encryption secrets.
#   - Never writes credentials to disk.
#   - Reads credentials only from the current shell or .env.local.
#   - Does not use token/*.json.
set -euo pipefail

readonly DEV_FUNCTION_NAME="dev-fn-notion-sync-gcal"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOCAL_ENV_FILE="${REPO_ROOT}/.env.local"
LOCAL_NOTION_CONFIG="${REPO_ROOT}/config/local.notion-setting.json"

MODE=""
UUID=""
DRY_RUN=0
VERBOSE=0

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --mode local [--dry-run] [--verbose]
  $(basename "$0") --mode cloud --uuid UUID [--dry-run] [--verbose]

Runs the Notion-GCal sync locally using the explicit APP_MODE flow.

Modes:
  local   Uses .env.local and config/local.notion-setting.json only. AWS credentials are not required.
  cloud   Uses local code with dev AWS-backed config for the supplied user UUID.

Options:
  --mode MODE      Required. Must be 'local' or 'cloud'.
  --uuid UUID      Required in cloud mode. Not used in local mode.
  --dry-run        Validate prerequisites without running the sync.
  --verbose        Enable DEBUG-level logging in the Python helper.
  -h, --help       Show this message.

Examples:
  ./scripts/local-run-dev-sync.sh --mode local
  ./scripts/local-run-dev-sync.sh --mode cloud --uuid xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
EOF
  exit 0
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  local cmd="$1"
  command -v "${cmd}" >/dev/null 2>&1 || fail "Required command '${cmd}' is not installed."
}

require_env() {
  local name="$1"
  [[ -n "${!name:-}" ]] || fail "${name} is required but is not set."
}

load_dotenv_file() {
  local file="$1"
  local line key value

  [[ -f "${file}" ]] || fail "${file} does not exist. Create it from .env.local.example."

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"

    [[ -z "${line}" || "${line}" == \#* ]] && continue
    [[ "${line}" == export[[:space:]]* ]] && line="${line#export }"

    if [[ ! "${line}" =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]; then
      fail "Invalid line in ${file}. Use KEY=value entries only."
    fi

    key="${line%%=*}"
    value="${line#*=}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"

    if [[ "${value}" == \"*\" && "${value}" == *\" && ${#value} -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "${value}" == \'*\' && "${value}" == *\' && ${#value} -ge 2 ]]; then
      value="${value:1:${#value}-2}"
    fi

    export "${key}=${value}"
  done < "${file}"
}

resolve_region() {
  local region="${APP_REGION:-${AWS_REGION:-}}"
  [[ -n "${region}" ]] || fail "Region is required. Set APP_REGION, or AWS_REGION."
  export APP_REGION="${region}"
  export AWS_REGION="${region}"
  echo "${region}"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)
        [[ $# -ge 2 ]] || fail "--mode requires a value."
        MODE="$2"
        shift 2
        ;;
      --uuid)
        [[ $# -ge 2 ]] || fail "--uuid requires a value."
        UUID="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --verbose)
        VERBOSE=1
        shift
        ;;
      -h|--help)
        usage
        ;;
      *)
        fail "Unknown flag: $1. Run with --help for usage."
        ;;
    esac
  done

  [[ -n "${MODE}" ]] || fail "--mode is required. Use --mode local or --mode cloud."
  [[ "${MODE}" == "local" || "${MODE}" == "cloud" ]] || fail "--mode must be 'local' or 'cloud'."
}

validate_local_mode() {
  echo "=== Notion-GCal Local Runner ==="
  echo "Mode: local"
  echo ""

  require_command uv
  require_command python3

  load_dotenv_file "${LOCAL_ENV_FILE}"

  [[ "${APP_MODE:-}" == "local" ]] || fail ".env.local must set APP_MODE=local."
  require_env NOTION_TOKEN
  require_env GOOGLE_CLIENT_ID
  require_env GOOGLE_CLIENT_SECRET
  require_env GOOGLE_REFRESH_TOKEN
  [[ -f "${LOCAL_NOTION_CONFIG}" ]] || fail "${LOCAL_NOTION_CONFIG} does not exist. Create it from config/local.notion-setting.example.json."

  export APP_MODE=local

  echo "Local prerequisites passed."
  echo "  .env.local: present"
  echo "  config/local.notion-setting.json: present"
  echo "  APP_MODE: local"
}

validate_cloud_mode() {
  local region identity_json caller_account caller_arn lambda_env_json

  [[ -n "${UUID}" ]] || fail "--uuid is required in cloud mode."

  echo "=== Notion-GCal Local Runner ==="
  echo "Mode: cloud"
  echo ""

  require_command aws
  require_command jq
  require_command uv
  require_command python3

  require_env AWS_ACCESS_KEY_ID
  require_env AWS_SECRET_ACCESS_KEY
  require_env AWS_SESSION_TOKEN
  region="$(resolve_region)"

  echo "Verifying AWS identity..."
  if ! identity_json="$(aws sts get-caller-identity --output json --no-cli-pager 2>&1)"; then
    echo "ERROR: aws sts get-caller-identity failed. Credentials may be expired or invalid." >&2
    echo "aws error: ${identity_json}" >&2
    exit 1
  fi

  caller_account="$(echo "${identity_json}" | jq -r '.Account')"
  caller_arn="$(echo "${identity_json}" | jq -r '.Arn')"

  echo "AWS Account ID: ${caller_account}"
  echo "AWS ARN:        ${caller_arn}"
  echo "Region:         ${region}"

  if [[ -n "${EXPECTED_AWS_ACCOUNT_ID:-}" && "${caller_account}" != "${EXPECTED_AWS_ACCOUNT_ID}" ]]; then
    echo "" >&2
    echo "ERROR: Credential account mismatch." >&2
    echo "  Expected account: ${EXPECTED_AWS_ACCOUNT_ID}" >&2
    echo "  Actual account:   ${caller_account}" >&2
    exit 1
  fi

  echo ""
  echo "Loading dev Lambda environment config from '${DEV_FUNCTION_NAME}'..."
  if ! lambda_env_json="$(
    aws lambda get-function-configuration \
      --function-name "${DEV_FUNCTION_NAME}" \
      --region "${region}" \
      --query 'Environment.Variables' \
      --output json \
      --no-cli-pager 2>&1
  )"; then
    echo "ERROR: Failed to fetch Lambda environment variables." >&2
    echo "       Ensure credentials can call lambda:GetFunctionConfiguration on '${DEV_FUNCTION_NAME}'." >&2
    exit 1
  fi

  export_lambda_var() {
    local key="$1"
    local value
    value="$(echo "${lambda_env_json}" | jq -r --arg k "${key}" '.[$k] // empty')"
    if [[ -n "${value}" ]]; then
      export "${key}=${value}"
    fi
  }

  for name in \
    DYNAMODB_USER_TABLE \
    DYNAMODB_SYNC_LOGS_TABLE \
    DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE \
    DYNAMODB_NOTION_OAUTH_TOKEN_TABLE \
    TOKEN_ENCRYPTION_KEY \
    GOOGLE_CALENDAR_CLIENT_ID \
    GOOGLE_CALENDAR_CLIENT_SECRET \
    APP_MODE \
    APP_STAGE; do
    export_lambda_var "${name}"
  done
  unset name lambda_env_json

  [[ "${APP_MODE:-}" == "cloud" ]] || fail "Dev Lambda environment must set APP_MODE=cloud."
  export APP_MODE=cloud
  export APP_REGION="${region}"
  export AWS_REGION="${region}"

  for name in \
    DYNAMODB_USER_TABLE \
    DYNAMODB_SYNC_LOGS_TABLE \
    DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE \
    DYNAMODB_NOTION_OAUTH_TOKEN_TABLE \
    TOKEN_ENCRYPTION_KEY \
    GOOGLE_CALENDAR_CLIENT_ID \
    GOOGLE_CALENDAR_CLIENT_SECRET \
    APP_REGION; do
    require_env "${name}"
  done
  unset name

  echo "Cloud prerequisites passed."
  echo "  APP_MODE: cloud"
  echo "  UUID: ${UUID}"
  echo "  DYNAMODB_USER_TABLE: [set, not printed]"
  echo "  DYNAMODB_SYNC_LOGS_TABLE: [set, not printed]"
  echo "  DYNAMODB_GOOGLE_OAUTH_TOKEN_TABLE: [set, not printed]"
  echo "  DYNAMODB_NOTION_OAUTH_TOKEN_TABLE: [set, not printed]"
  echo "  TOKEN_ENCRYPTION_KEY: [set, not printed]"
  echo "  GOOGLE_CALENDAR_CLIENT_ID: [set, not printed]"
  echo "  GOOGLE_CALENDAR_CLIENT_SECRET: [set, not printed]"
}

run_helper() {
  local invoke_args

  invoke_args=("--mode" "${MODE}")
  if [[ "${MODE}" == "cloud" ]]; then
    invoke_args+=("--uuid" "${UUID}")
  fi
  [[ "${VERBOSE}" -eq 1 ]] && invoke_args+=("--verbose")

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo ""
    echo "=== DRY RUN ==="
    echo "All prerequisites passed."
    echo "Would invoke: uv run python scripts/local_invoke_sync_lambda.py ${invoke_args[*]}"
    return 0
  fi

  echo ""
  echo "=== Invoking Sync ==="
  cd "${REPO_ROOT}"
  uv run python scripts/local_invoke_sync_lambda.py "${invoke_args[@]}"
}

parse_args "$@"

case "${MODE}" in
  local) validate_local_mode ;;
  cloud) validate_cloud_mode ;;
esac

run_helper
