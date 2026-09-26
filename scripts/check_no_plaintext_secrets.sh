#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR=".github/workflows"
if [[ ! -d "$TARGET_DIR" ]]; then
  echo "No $TARGET_DIR directory found; skipping secret check."
  exit 0
fi

python3 - "$TARGET_DIR" <<'PY'
import re
import sys
from pathlib import Path

target = Path(sys.argv[1])
workflow_files = sorted(
    [*target.rglob("*.yml"), *target.rglob("*.yaml")],
    key=lambda path: str(path),
)

sensitive_keys = re.compile(
    r"TOKEN_ENCRYPTION_KEY|GOOGLE_CALENDAR_CLIENT_SECRET|GOOGLE_CALENDAR_CLIENT_ID"
)
secrets_reference = re.compile(r"\$\{\{\s*secrets\.")
env_dump = re.compile(
    r"^\s*(?:run:\s*)?(?:printenv|env)(?:\s|$)"
    r"|toJson\(\s*(?:env|secrets)\s*\)"
)

hard_coded = []
env_dumps = []

for path in workflow_files:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if sensitive_keys.search(line) and not secrets_reference.search(line):
            hard_coded.append(f"{path}:{line_number}:{line}")
        if env_dump.search(line):
            env_dumps.append(f"{path}:{line_number}:{line}")

if hard_coded:
    print("Found potentially hard-coded sensitive values in workflow files:", file=sys.stderr)
    print("\n".join(hard_coded), file=sys.stderr)
    print("Use GitHub secrets syntax instead of plaintext values.", file=sys.stderr)
    raise SystemExit(1)

if env_dumps:
    print("Found forbidden env/secrets dump patterns in workflow files:", file=sys.stderr)
    print("\n".join(env_dumps), file=sys.stderr)
    print("Remove commands like printenv, bare env, or toJson(env/secrets).", file=sys.stderr)
    raise SystemExit(1)

print("Workflow secret guard passed.")
PY
