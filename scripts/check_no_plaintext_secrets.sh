#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR=".github/workflows"
if [[ ! -d "$TARGET_DIR" ]]; then
  echo "No $TARGET_DIR directory found; skipping secret check."
  exit 0
fi

# Project-specific sensitive keys that must never be hard-coded in workflow YAML.
SENSITIVE_KEYS_REGEX='TOKEN_ENCRYPTION_KEY|GOOGLE_CALENDAR_CLIENT_SECRET|GOOGLE_CALENDAR_CLIENT_ID'
ENV_DUMP_PATTERNS_REGEX='^[[:space:]]*(run:[[:space:]]*)?(printenv|env)([[:space:]]|$)|toJson\(\s*env\s*\)|toJson\(\s*secrets\s*\)|\$\{\{\s*toJson\(\s*env\s*\)\s*\}\}|\$\{\{\s*toJson\(\s*secrets\s*\)\s*\}\}'

# Find suspicious lines that mention sensitive keys but do not use GitHub secrets interpolation.
# Allowlist examples:
#   SOME_KEY: ${{ secrets.SOME_KEY }}
#   "SOME_KEY": "${{ secrets.SOME_KEY }}"
violations="$(rg -n --glob '*.yml' --glob '*.yaml' "${SENSITIVE_KEYS_REGEX}" "$TARGET_DIR" | rg -v '\$\{\{\s*secrets\.' || true)"

if [[ -n "$violations" ]]; then
  echo "Found potentially hard-coded sensitive values in workflow files:"
  echo "$violations"
  echo "Use GitHub secrets syntax (\${{ secrets.NAME }}) instead of plaintext values."
  exit 1
fi

# Detect potential environment dump patterns in workflows.
# This blocks obvious full env/secrets logging patterns in CI logs.
env_dump_violations="$(rg -n --glob '*.yml' --glob '*.yaml' -P "${ENV_DUMP_PATTERNS_REGEX}" "$TARGET_DIR" || true)"

if [[ -n "$env_dump_violations" ]]; then
  echo "Found forbidden env/secrets dump patterns in workflow files:"
  echo "$env_dump_violations"
  echo "Remove commands like 'printenv', bare 'env', or toJson(env/secrets) from workflows."
  exit 1
fi

echo "Workflow secret guard passed."
