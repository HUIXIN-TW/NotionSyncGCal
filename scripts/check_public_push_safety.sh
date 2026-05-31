#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STAGED_FILES=()
while IFS= read -r file; do
  STAGED_FILES+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACMR)

if [[ ${#STAGED_FILES[@]} -eq 0 ]]; then
  echo "No staged files; skipping public push safety checks."
  exit 0
fi

for file in "${STAGED_FILES[@]}"; do
  case "$file" in
    *"/logs/"*|logs/*|*.log|get_gcal_event.json|get_notion_task.json)
      echo "Blocked: staged file looks like runtime log data: $file"
      exit 1
      ;;
    .env|.env.*|token/*)
      echo "Blocked: staged file is a local secret/config path: $file"
      exit 1
      ;;
  esac
done

SECRET_PATTERN='(BEGIN (RSA|EC|OPENSSH) PRIVATE KEY|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z\-_]{35}|xox[baprs]-[0-9A-Za-z-]{20,})'

for file in "${STAGED_FILES[@]}"; do
  if ! git cat-file -e ":$file" 2>/dev/null; then
    continue
  fi
  if git show ":$file" | rg -n --no-heading -e "$SECRET_PATTERN" >/dev/null; then
    echo "Blocked: potential credential detected in staged file: $file"
    git show ":$file" | rg -n --no-heading -e "$SECRET_PATTERN" || true
    exit 1
  fi
done

echo "Public push safety checks passed for staged files."
