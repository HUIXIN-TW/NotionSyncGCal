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

    function trim(value) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      return value
    }

    function list_allows_master(value) {
      return value ~ /(^|[^A-Za-z0-9_*.-])(master|\*\*)([^A-Za-z0-9_*.-]|$)/
    }

    function close_push_if_needed(line) {
      if (in_push && indent(line) <= push_indent && line !~ /^[[:space:]]*$/) {
        if (!push_has_branches || push_allows_master) {
          master_seen = 1
        }
        in_push = 0
        in_branches = 0
      }
    }

    /^[[:space:]]*#/ { next }

    /^on:[[:space:]]*\[[^]]*push[^]]*\]/ {
      push_seen = 1
      master_seen = 1
      next
    }

    /^on:[[:space:]]*push[[:space:]]*$/ {
      push_seen = 1
      master_seen = 1
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

    in_on {
      close_push_if_needed($0)
    }

    in_on && indent($0) == on_indent + 2 && /^[[:space:]]+push:[[:space:]]*$/ {
      push_seen = 1
      in_push = 1
      in_branches = 0
      push_has_branches = 0
      push_allows_master = 0
      push_indent = indent($0)
      next
    }

    in_push && indent($0) == push_indent + 2 && /^[[:space:]]+branches:[[:space:]]*/ {
      push_has_branches = 1
      in_branches = 1
      branches_indent = indent($0)

      branch_value = $0
      sub(/^[[:space:]]+branches:[[:space:]]*/, "", branch_value)
      if (list_allows_master(branch_value)) {
        push_allows_master = 1
      }
      next
    }

    in_branches && indent($0) <= branches_indent && $0 !~ /^[[:space:]]*$/ {
      in_branches = 0
    }

    in_branches && /^[[:space:]]+-[[:space:]]*/ {
      branch_value = $0
      sub(/^[[:space:]]+-[[:space:]]*/, "", branch_value)
      branch_value = trim(branch_value)
      gsub(/^["'\'']|["'\'']$/, "", branch_value)
      if (branch_value == "master" || branch_value == "**") {
        push_allows_master = 1
      }
    }

    END {
      if (in_push && (!push_has_branches || push_allows_master)) {
        master_seen = 1
      }
      exit !(push_seen && master_seen)
    }
  ' "$file"
}

is_workflow_dispatch_only() {
  local file="$1"

  awk '
    function indent(line) {
      match(line, /^[ ]*/)
      return RLENGTH
    }

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
      on_indent = indent($0)
      next
    }

    in_on && indent($0) <= on_indent && $0 !~ /^[[:space:]]*$/ {
      in_on = 0
    }

    in_on && /^[[:space:]]+[A-Za-z_]+:/ {
      if (indent($0) != on_indent + 2) {
        next
      }

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
  grep -q "aws[[:space:]]*lambda[[:space:]]*update-function-code" "$1"
}

contains_aws_ecr_command() {
  grep -q "aws[[:space:]]*ecr[[:space:]]" "$1"
}

contains_docker_push_true() {
  grep -qE '^[[:space:]]*push:[[:space:]]*true[[:space:]]*$' "$1"
}

contains_required_literal() {
  local file="$1"
  local literal="$2"

  grep -qF "$literal" "$file"
}

check_dev_deploy_metadata_is_indirect() {
  local file="$1"
  local violations=""
  local key
  local count

  violations="$(
    grep -En '(^|[^0-9])[0-9]{12}([^0-9]|$)|(^|[^a-z0-9])[a-z]{2}(-[a-z0-9]+)+-[0-9]([^a-z0-9]|$)|\.dkr\.ecr\.' "$file" || true
  )"
  if [[ -n "$violations" ]]; then
    report_failure "$file must not contain hard-coded AWS account, region, or ECR registry metadata:"
    echo "$violations"
  fi

  for key in AWS_REGION ECR_ACCOUNT_ID IMAGE_NAME FUNCTION_NAME; do
    count="$(grep -Ec "^[[:space:]]*${key}:" "$file" || true)"
    if [[ "$count" -ne 1 ]]; then
      report_failure "$file must define ${key} exactly once through its approved environment-variable mapping."
    fi
  done

  violations="$(
    grep -En '^[[:space:]]*registries:' "$file" | grep -vF '${{ env.ECR_ACCOUNT_ID }}' || true
  )"
  if [[ -n "$violations" ]]; then
    report_failure "$file must source ECR login registries from env.ECR_ACCOUNT_ID:"
    echo "$violations"
  fi

  violations="$(
    grep -En '\$\{\{[[:space:]]*steps\.login-ecr\.outputs\.registry[[:space:]]*\}\}' "$file" | grep -vF '${{ env.IMAGE_NAME }}' || true
  )"
  if [[ -n "$violations" ]]; then
    report_failure "$file must build ECR image references with env.IMAGE_NAME:"
    echo "$violations"
  fi

  violations="$(
    grep -En -- '--function-name' "$file" | grep -vF '${{ env.FUNCTION_NAME }}' || true
  )"
  if [[ -n "$violations" ]]; then
    report_failure "$file must source Lambda function arguments from env.FUNCTION_NAME:"
    echo "$violations"
  fi

  violations="$(
    grep -En -- '--region' "$file" | grep -vF '${{ env.AWS_REGION }}' || true
  )"
  if [[ -n "$violations" ]]; then
    report_failure "$file must source AWS CLI region arguments from env.AWS_REGION:"
    echo "$violations"
  fi
}

check_dev_validation_precedes_aws_access() {
  local file="$1"
  local validation_line
  local aws_credentials_line

  validation_line="$(grep -nF './scripts/validate_dev_deploy_config.sh' "$file" | head -n 1 | cut -d: -f1 || true)"
  aws_credentials_line="$(grep -nF 'aws-actions/configure-aws-credentials@' "$file" | head -n 1 | cut -d: -f1 || true)"

  if [[ -z "$validation_line" ]]; then
    report_failure "$file must run validate_dev_deploy_config.sh."
    return
  fi

  if [[ -z "$aws_credentials_line" ]]; then
    report_failure "$file must configure AWS credentials through the approved OIDC action."
    return
  fi

  if (( validation_line >= aws_credentials_line )); then
    report_failure "$file must validate deployment configuration before the first AWS credential step."
  fi
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
    grep -En '^[[:space:]]*(run:[[:space:]]*)?(printenv|env)([[:space:]]|$)|^[[:space:]]*(run:[[:space:]]*)?set[[:space:]]+-x([[:space:]]|$)' "${files[@]}" || true
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

check_aws_cli_output_safety() {
  local scope_name="$1"
  shift
  local files=("$@")
  local violations=""

  if [[ ${#files[@]} -eq 0 ]]; then
    return 0
  fi

  violations="$(
    awk '
      function starts_checked_command(line) {
        return line ~ /aws[[:space:]]+lambda[[:space:]]+(update-function-code|get-function-configuration|get-function|update-function-configuration)([[:space:]\\]|$)/ \
          || line ~ /aws[[:space:]]+ecr[[:space:]]+describe-images([[:space:]\\]|$)/
      }

      function continues(line) {
        return line ~ /\\[[:space:]]*$/
      }

      function finish_command() {
        if (command == "") {
          return
        }

        if (command ~ /aws[[:space:]]+lambda[[:space:]]+update-function-code([[:space:]\\]|$)/) {
          if (command !~ /--query[[:space:]]+['\''"]?LastUpdateStatus['\''"]?/ || command !~ /--output[[:space:]]+text([[:space:]\\]|$)/) {
            print FILENAME ":" start_line ": aws lambda update-function-code must include --query '\''LastUpdateStatus'\'' and --output text."
          }
        }

        if (command ~ /aws[[:space:]]+ecr[[:space:]]+describe-images([[:space:]\\]|$)/) {
          if (command !~ /--query[[:space:]]+['\''"]?imageDetails\[0\]\.imageDigest['\''"]?/ || command !~ /--output[[:space:]]+text([[:space:]\\]|$)/) {
            print FILENAME ":" start_line ": aws ecr describe-images must include --query '\''imageDetails[0].imageDigest'\'' and --output text."
          }
        }

        if (command ~ /aws[[:space:]]+lambda[[:space:]]+(get-function-configuration|get-function|update-function-configuration)([[:space:]\\]|$)/) {
          if (command !~ /--query[[:space:]]+/ || command ~ /Environment/) {
            print FILENAME ":" start_line ": aws lambda get/update function configuration commands must not print full configuration or Environment values."
          }
        }

        command = ""
        start_line = 0
      }

      FNR == 1 {
        finish_command()
      }

      {
        if (command != "") {
          command = command " " $0
          if (!continues($0)) {
            finish_command()
          }
          next
        }

        if (starts_checked_command($0)) {
          command = $0
          start_line = FNR
          if (!continues($0)) {
            finish_command()
          }
        }
      }

      END {
        finish_command()
      }
    ' "${files[@]}" || true
  )"

  if [[ -n "$violations" ]]; then
    if [[ "$scope_name" == "active" ]]; then
      report_failure "Active workflows must constrain AWS Lambda/ECR CLI output:"
      echo "$violations"
    else
      echo "WARNING: Disabled legacy workflows contain AWS Lambda/ECR CLI output issues:"
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
check_aws_cli_output_safety "active" "${active_files[@]}"
check_aws_cli_output_safety "disabled" "${disabled_files[@]}"

for file in "${active_files[@]}"; do
  if has_master_push_trigger "$file"; then
    contains_update_function_code "$file" \
      && report_failure "$file is triggered by push to master and calls aws lambda update-function-code."
    contains_required_literal "$file" "docker/build-push-action" \
      && report_failure "$file is triggered by push to master and uses docker/build-push-action."
    contains_required_literal "$file" "aws-actions/amazon-ecr-login" \
      && report_failure "$file is triggered by push to master and logs in to Amazon ECR."
    contains_required_literal "$file" "aws-actions/configure-aws-credentials" \
      && report_failure "$file is triggered by push to master and configures AWS credentials."
    contains_required_literal "$file" "PRD_DEPLOY_ROLE_ARN" \
      && report_failure "$file is triggered by push to master and references PRD_DEPLOY_ROLE_ARN."
    contains_required_literal "$file" "PRD_ECR_PUSH_ROLE_ARN" \
      && report_failure "$file is triggered by push to master and references PRD_ECR_PUSH_ROLE_ARN."
    contains_required_literal "$file" "PRD_LAMBDA_DEPLOY_ROLE_ARN" \
      && report_failure "$file is triggered by push to master and references PRD_LAMBDA_DEPLOY_ROLE_ARN."
    contains_aws_ecr_command "$file" \
      && report_failure "$file is triggered by push to master and runs aws ecr commands."
    contains_docker_push_true "$file" \
      && report_failure "$file is triggered by push to master and enables Docker image push."
  fi
done

dev_workflow="${WORKFLOW_DIR}/deploy-dev-lambda.yml"
if [[ -f "$dev_workflow" ]]; then
  contains_required_literal "$dev_workflow" "DEV_DEPLOY_ROLE_ARN" || report_failure "$dev_workflow must reference DEV_DEPLOY_ROLE_ARN."
  contains_required_literal "$dev_workflow" 'AWS_REGION: ${{ vars.DEV_AWS_REGION }}' || report_failure "$dev_workflow must source AWS_REGION from vars.DEV_AWS_REGION."
  contains_required_literal "$dev_workflow" 'ECR_ACCOUNT_ID: ${{ vars.DEV_ECR_ACCOUNT_ID }}' || report_failure "$dev_workflow must source ECR_ACCOUNT_ID from vars.DEV_ECR_ACCOUNT_ID."
  contains_required_literal "$dev_workflow" 'IMAGE_NAME: ${{ vars.DEV_ECR_REPOSITORY }}' || report_failure "$dev_workflow must source IMAGE_NAME from vars.DEV_ECR_REPOSITORY."
  contains_required_literal "$dev_workflow" 'FUNCTION_NAME: ${{ vars.DEV_LAMBDA_FUNCTION_NAME }}' || report_failure "$dev_workflow must source FUNCTION_NAME from vars.DEV_LAMBDA_FUNCTION_NAME."
  check_dev_deploy_metadata_is_indirect "$dev_workflow"
  check_dev_validation_precedes_aws_access "$dev_workflow"
else
  report_failure "$dev_workflow is missing."
fi

production_workflows=()
while IFS= read -r file; do
  production_workflows+=("$file")
done < <(printf "%s\n" "${active_files[@]}" | grep -iE '(^|/).*(prd|prod|production).*deploy.*\.ya?ml$|(^|/).*deploy.*(prd|prod|production).*\.ya?ml$' || true)

if [[ ${#production_workflows[@]} -eq 0 ]]; then
  echo "No active production deploy workflow found; production-specific guardrails will apply once it exists."
else
  for file in "${production_workflows[@]}"; do
    is_workflow_dispatch_only "$file" || report_failure "$file must be triggered by workflow_dispatch only."
    contains_required_literal "$file" "PRD_DEPLOY_ROLE_ARN" || report_failure "$file must reference PRD_DEPLOY_ROLE_ARN."
    contains_required_literal "$file" 'vars.PRD_AWS_REGION' || report_failure "$file must source its AWS region from an approved PRD environment variable."
    contains_required_literal "$file" 'vars.PRD_ECR_ACCOUNT_ID' || report_failure "$file must source its ECR account from an approved PRD environment variable."
    contains_required_literal "$file" 'vars.PRD_ECR_REPOSITORY' || report_failure "$file must source its ECR repository from an approved PRD environment variable."
    contains_required_literal "$file" 'vars.PRD_FUNCTION_NAME' || report_failure "$file must source its Lambda function from an approved PRD environment variable."
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
