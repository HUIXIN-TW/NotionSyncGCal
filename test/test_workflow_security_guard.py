import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "check_workflow_security.py"
SPEC = importlib.util.spec_from_file_location("workflow_security_guard", SCRIPT_PATH)
WORKFLOW_SECURITY_GUARD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKFLOW_SECURITY_GUARD)


class WorkflowSecurityGuardTests(unittest.TestCase):
    def _check(self, workflows):
        with tempfile.TemporaryDirectory() as temporary_directory:
            workflow_dir = Path(temporary_directory)
            for relative_path, content in workflows.items():
                path = workflow_dir / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            return WORKFLOW_SECURITY_GUARD.check_workflow_security(workflow_dir)

    def test_top_level_permissions_pass(self):
        errors = self._check(
            {
                "safe.yml": """name: Safe
on: push
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo safe
"""
            }
        )
        self.assertEqual([], errors)

    def test_job_level_permissions_pass(self):
        errors = self._check(
            {
                "safe.yml": """name: Safe
on: issues
jobs:
  mutate:
    runs-on: ubuntu-latest
    permissions:
      issues: write
    steps:
      - run: echo safe
"""
            }
        )
        self.assertEqual([], errors)

    def test_missing_permissions_fail(self):
        errors = self._check(
            {
                "unsafe.yml": """name: Unsafe
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo unsafe
"""
            }
        )
        self.assertTrue(any("permission boundary" in error for error in errors))

    def test_event_expression_in_run_fails(self):
        errors = self._check(
            {
                "unsafe.yml": """name: Unsafe
on: issues
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "${{ github.event.issue.title }}"
"""
            }
        )
        self.assertTrue(any("executable source" in error for error in errors))

    def test_event_expression_in_github_script_fails(self):
        errors = self._check(
            {
                "unsafe.yml": """name: Unsafe
on: pull_request
permissions:
  pull-requests: write
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/github-script@v9
        with:
          script: |
            const branch = "${{ github.head_ref }}";
"""
            }
        )
        self.assertTrue(any("executable source" in error for error in errors))

    def test_pull_request_target_checkout_fails(self):
        errors = self._check(
            {
                "unsafe.yml": """name: Unsafe
on: pull_request_target
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
"""
            }
        )
        self.assertTrue(any("pull_request_target" in error for error in errors))

    def test_disabled_workflows_are_ignored(self):
        errors = self._check(
            {
                "safe.yml": """name: Safe
on: push
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo safe
""",
                "disabled/legacy.yml": """name: Legacy
on: pull_request_target
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
""",
            }
        )
        self.assertEqual([], errors)

    def test_repository_active_workflows_pass(self):
        errors = WORKFLOW_SECURITY_GUARD.check_workflow_security(
            ROOT / ".github" / "workflows"
        )
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
