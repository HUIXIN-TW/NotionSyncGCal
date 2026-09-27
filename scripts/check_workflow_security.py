#!/usr/bin/env python3

import re
import sys
from pathlib import Path

DIRECT_EVENT_EXPRESSION = re.compile(
    r"\$\{\{\s*github\.(?:event\b|head_ref\b|ref\b|ref_name\b)"
)
EXECUTABLE_KEY = re.compile(r"^(\s*)(run|script):(?:\s*(.*))?$")
JOB_KEY = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
JOB_PERMISSION = re.compile(r"^    permissions:\s*(?:.*)?$")
TOP_LEVEL_PERMISSION = re.compile(r"^permissions:\s*(?:.*)?$")


def active_workflow_files(workflow_dir: Path) -> list[Path]:
    files = [*workflow_dir.rglob("*.yml"), *workflow_dir.rglob("*.yaml")]
    return sorted(
        path
        for path in files
        if "disabled" not in path.relative_to(workflow_dir).parts
    )


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _job_ranges(lines: list[str]) -> list[tuple[str, int, int]]:
    jobs_index = next(
        (index for index, line in enumerate(lines) if line == "jobs:"),
        None,
    )
    if jobs_index is None:
        return []

    jobs: list[tuple[str, int]] = []
    for index in range(jobs_index + 1, len(lines)):
        line = lines[index]
        if line and not line.startswith(" ") and not line.lstrip().startswith("#"):
            break
        match = JOB_KEY.match(line)
        if match:
            jobs.append((match.group(1), index))

    ranges = []
    for position, (name, start) in enumerate(jobs):
        end = jobs[position + 1][1] if position + 1 < len(jobs) else len(lines)
        ranges.append((name, start, end))
    return ranges


def _permission_errors(path: Path, lines: list[str]) -> list[str]:
    if any(TOP_LEVEL_PERMISSION.match(line) for line in lines):
        return []

    jobs = _job_ranges(lines)
    if not jobs:
        return [f"{path}: active workflow has no explicit permission boundary"]

    errors = []
    for job_name, start, end in jobs:
        if not any(JOB_PERMISSION.match(line) for line in lines[start:end]):
            errors.append(
                f"{path}: job '{job_name}' has no explicit permission boundary"
            )
    return errors


def _executable_expression_errors(path: Path, lines: list[str]) -> list[str]:
    errors = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = EXECUTABLE_KEY.match(line)
        if not match:
            index += 1
            continue

        base_indent = len(match.group(1))
        inline = match.group(3) or ""
        if DIRECT_EVENT_EXPRESSION.search(inline):
            errors.append(
                f"{path}:{index + 1}: contributor-controlled GitHub expression "
                "is embedded directly in executable source"
            )

        index += 1
        while index < len(lines):
            nested = lines[index]
            if nested.strip() and _indent(nested) <= base_indent:
                break
            if DIRECT_EVENT_EXPRESSION.search(nested):
                errors.append(
                    f"{path}:{index + 1}: contributor-controlled GitHub expression "
                    "is embedded directly in executable source"
                )
            index += 1
    return errors


def _pull_request_target_errors(path: Path, lines: list[str]) -> list[str]:
    uncommented = "\n".join(
        line for line in lines if not line.lstrip().startswith("#")
    )
    if "pull_request_target" not in uncommented:
        return []
    if re.search(r"uses:\s*actions/checkout@", uncommented):
        return [
            f"{path}: pull_request_target workflow must not checkout "
            "contributor-controlled code"
        ]
    return []


def check_workflow_security(workflow_dir: Path) -> list[str]:
    errors = []
    for path in active_workflow_files(workflow_dir):
        lines = path.read_text(encoding="utf-8").splitlines()
        errors.extend(_permission_errors(path, lines))
        errors.extend(_executable_expression_errors(path, lines))
        errors.extend(_pull_request_target_errors(path, lines))
    return errors


def main() -> int:
    workflow_dir = Path(".github/workflows")
    if not workflow_dir.is_dir():
        print("No .github/workflows directory found; skipping workflow security guard.")
        return 0

    errors = check_workflow_security(workflow_dir)
    if errors:
        print("Workflow security guard failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("Workflow security guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
