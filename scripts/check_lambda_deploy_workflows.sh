#!/usr/bin/env bash
set -euo pipefail

WORKFLOW_DIR=".github/workflows"
DISABLED_WORKFLOW_DIR="${WORKFLOW_DIR}/disabled"

if [[ ! -d "$WORKFLOW_DIR" ]]; then
  echo "No $WORKFLOW_DIR directory found; skipping Lambda deploy workflow guardrails."
  exit 0
fi

failures=0

report_failure() {
  echo "ERROR: $1"
  failures=$((failures + 1))
}

workflow_files() {
  find "$WORKFLOW_DIR" \
    -path "$DISABLED_WORKFLOW_DIR" -prune -o \
    -type f \( -name "*.yml" -o -name "*.yaml" \) \
    -print
}

disabled_workflow_files() {
  if [[ -d "$DISABLED_WORKFLOW_DIR" ]]; then
    find "$DISABLED_WORKFLOW_DIR" -type f \( -name "*.yml" -o -name "*.yaml" -o -name "*.disabled" \) -print
  fi
}

has_master_push_trigger() {
  local file="$1"

  awk '
    function indent(line) {
      match(line, /^[ ]*/)
      return RLENGTH
    }

    /^[[:space:]]*#/ { next }

    /^on:[[:space:]]*\[[^]]*push[^]]*\]/ {
      push_seen = 1
      next
    }

    /^on:[[:space:]]*push[[:space:]]*$/ {
      push_seen = 1
      next
    }

    /^on:[[:space:]]*$/ {
      in_on = 1
      on_indent = indent($0)
      next
    }

    in_on && indent($0) <= on_indent && $0 !~ /^[[:space:]]*$/ {
      in_on = 0
    }

    in_on && /^[[:space:]]+push:[[:space:]]*$/ {
      push_seen = 1
      push_indent = indent($0)
      next
    }

    push_seen && /^[[:space:]]+branches:[[:space:]]*\[[^]]*master[^]]*\]/ {
      master_seen = 1
    }

    push_seen && /^[[:space:]]+-[[:space:]]*master[[:space:]]*$/ {
      master_seen = 1
    }

    push_seen && indent($0) <= push_indent && $0 !~ /^[[:space:]]*$/ && $0 !~ /^[[:space:]]+push:[[:space:]]*$/ {
      push_indent = -1
    }

    END {
      exit !(push_seen && master_seen)
    }
  ' "$file"
}

is_workflow_dispatch_only() {
  local file="$1"

  awk '
    function trim(value) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      return value
    }

    /^[[:space:]]*#/ { next }

    /^on:[[:space:]]*workflow_dispatch[[:space:]]*$/ {
      dispatch_seen = 1
      next
    }

    /^on:[[:space:]]*\[[^]]*workflow_dispatch[^]]*\]/ {
      dispatch_seen = 1
      if ($0 !~ /^on:[[:space:]]*\[[[:space:]]*workflow_dispatch[[:space:]]*\][[:space:]]*$/) {
        other_seen = 1
      }
      next
    }

    /^on:[[:space:]]*$/ {
      in_on = 1
      next
    }

    in_on && /^[^[:space:]]/ {
      in_on = 0
    }

    in_on && /^[[:space:]]+[A-Za-z_]+:/ {
      event = trim($0)
      sub(/:.*/, "", event)
      if (event == "workflow_dispatch") {
        dispatch_seen = 1
      } else {
        other_seen = 1
      }
    }

    END {
      exit !(dispatch_seen && !other_seen)
    }
  ' "$file"
}

contains_update_function_code() {
  rg -q "aws[[:space:]]+lambda[[:space:]]+update-function-code" "$1"
}

contains_required_literal() {
  local file="$1"
  local literal="$2"

  rg -q --fixed-strings "$literal" "$file"
}

check_no_forbidden_env_dumping() {
  local scope_name="$1"
  shift
  local files=("$@")
  local violations=""

  if [[ ${#files[@]} -eq 0 ]]; then
    return 0
  fi

  violations="$(
    rg -n -P '^[[:space:]]*(run:[[:space:]]*)?(printenv|env)([[:space:]]|$)|^[[:space:]]*(run:[[:space:]]*)?set[[:space:]]+-x([[:space:]]|$)' "${files[@]}" || true
  )"

  if [[ -n "$violations" ]]; then
    if [[ "$scope_name" == "active" ]]; then
      report_failure "Active workflows must not use printenv, bare env, or set -x:"
      echo "$violations"
    else
      echo "WARNING: Disabled legacy workflows contain env-dumping/debug patterns:"
      echo "$violations"
    fi
  fi
}

active_files=()
while IFS= read -r file; do
  active_files+=("$file")
done < <(workflow_files)

disabled_files=()
while IFS= read -r file; do
  disabled_files+=("$file")
done < <(disabled_workflow_files)

if [[ ${#active_files[@]} -eq 0 ]]; then
  echo "No active workflow YAML files found; skipping Lambda deploy workflow guardrails."
  exit 0
fi

check_no_forbidden_env_dumping "active" "${active_files[@]}"
check_no_forbidden_env_dumping "disabled" "${disabled_files[@]}"

for file in "${active_files[@]}"; do
  if has_master_push_trigger "$file" && contains_update_function_code "$file"; then
    report_failure "$file is triggered by push to master and calls aws lambda update-function-code."
  fi
done

dev_workflow="${WORKFLOW_DIR}/lambda-ecr-deploy.dev.yml"
if [[ -f "$dev_workflow" ]]; then
  contains_required_literal "$dev_workflow" "DEV_DEPLOY_ROLE_ARN" || report_failure "$dev_workflow must reference DEV_DEPLOY_ROLE_ARN."
  contains_required_literal "$dev_workflow" "ap-southeast-2" || report_failure "$dev_workflow must use AWS region ap-southeast-2."
  contains_required_literal "$dev_workflow" "262835400669" || report_failure "$dev_workflow must use ECR account 262835400669."
  contains_required_literal "$dev_workflow" "notion-sync-gcal-lambda" || report_failure "$dev_workflow must use image name notion-sync-gcal-lambda."
  contains_required_literal "$dev_workflow" "dev-fn-notion-sync-gcal" || report_failure "$dev_workflow must deploy only to dev-fn-notion-sync-gcal."
else
  report_failure "$dev_workflow is missing."
fi

production_workflows=()
while IFS= read -r file; do
  production_workflows+=("$file")
done < <(printf "%s\n" "${active_files[@]}" | rg -i '(^|/).*(prd|prod|production).*deploy.*\.ya?ml$|(^|/).*deploy.*(prd|prod|production).*\.ya?ml$' || true)

if [[ ${#production_workflows[@]} -eq 0 ]]; then
  echo "No active production deploy workflow found; production-specific guardrails will apply once it exists."
else
  for file in "${production_workflows[@]}"; do
    is_workflow_dispatch_only "$file" || report_failure "$file must be triggered by workflow_dispatch only."
    contains_required_literal "$file" "PRD_DEPLOY_ROLE_ARN" || report_failure "$file must reference PRD_DEPLOY_ROLE_ARN."
    contains_required_literal "$file" "ap-southeast-2" || report_failure "$file must use AWS region ap-southeast-2."
    contains_required_literal "$file" "262835400669" || report_failure "$file must use ECR account 262835400669."
    contains_required_literal "$file" "notion-sync-gcal-lambda" || report_failure "$file must use image name notion-sync-gcal-lambda."
  done
fi

for file in "${disabled_files[@]}"; do
  if contains_update_function_code "$file"; then
    echo "WARNING: Disabled legacy workflow contains aws lambda update-function-code: $file"
  fi

  if has_master_push_trigger "$file"; then
    echo "WARNING: Disabled legacy workflow has a push-to-master trigger: $file"
  fi
done

if [[ "$failures" -gt 0 ]]; then
  echo "Lambda deploy workflow guardrails failed with $failures issue(s)."
  exit 1
fi

echo "Lambda deploy workflow guardrails passed."
