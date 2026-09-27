import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOY_GUARD = ROOT / "scripts" / "check_lambda_deploy_workflows.sh"
CONFIG_VALIDATOR = ROOT / "scripts" / "validate_dev_deploy_config.sh"


class DevDeployConfigValidationTests(unittest.TestCase):
    def _run_validator(self, overrides=None, removed=None):
        env = os.environ.copy()
        env.update(
            {
                "AWS_REGION": "us-east-1",
                "ECR_ACCOUNT_ID": "123456789012",
                "IMAGE_NAME": "sample-worker",
                "FUNCTION_NAME": "dev-fn-sample-worker",
            }
        )
        for key in removed or []:
            env.pop(key, None)
        env.update(overrides or {})
        return subprocess.run(
            [str(CONFIG_VALIDATOR)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_valid_configuration_passes_without_echoing_values(self):
        result = self._run_validator()

        self.assertEqual(0, result.returncode)
        self.assertIn("validation passed", result.stdout.lower())
        self.assertNotIn("123456789012", result.stdout + result.stderr)
        self.assertNotIn("sample-worker", result.stdout + result.stderr)

    def test_missing_configuration_fails(self):
        result = self._run_validator(removed=["ECR_ACCOUNT_ID"])

        self.assertNotEqual(0, result.returncode)
        self.assertIn("DEV_ECR_ACCOUNT_ID is required", result.stderr)

    def test_invalid_region_fails(self):
        result = self._run_validator({"AWS_REGION": "not-a-region"})

        self.assertNotEqual(0, result.returncode)
        self.assertIn("DEV_AWS_REGION has an invalid format", result.stderr)

    def test_invalid_account_id_fails(self):
        result = self._run_validator({"ECR_ACCOUNT_ID": "1234"})

        self.assertNotEqual(0, result.returncode)
        self.assertIn("exactly 12 digits", result.stderr)

    def test_invalid_repository_name_fails(self):
        result = self._run_validator({"IMAGE_NAME": "Invalid Repository"})

        self.assertNotEqual(0, result.returncode)
        self.assertIn("DEV_ECR_REPOSITORY has an invalid format", result.stderr)

    def test_invalid_function_name_fails(self):
        result = self._run_validator({"FUNCTION_NAME": "invalid function name"})

        self.assertNotEqual(0, result.returncode)
        self.assertIn("DEV_LAMBDA_FUNCTION_NAME has an invalid format", result.stderr)


class LambdaDeployWorkflowGuardTests(unittest.TestCase):
    VALID_WORKFLOW = """name: Deploy Dev Lambda
on:
  push:
    branches:
      - dev
permissions:
  contents: read
  id-token: write
jobs:
  deploy:
    environment: dev
    env:
      AWS_REGION: ${{ vars.DEV_AWS_REGION }}
      ECR_ACCOUNT_ID: ${{ vars.DEV_ECR_ACCOUNT_ID }}
      IMAGE_NAME: ${{ vars.DEV_ECR_REPOSITORY }}
      FUNCTION_NAME: ${{ vars.DEV_LAMBDA_FUNCTION_NAME }}
    steps:
      - name: Validate deployment configuration
        run: ./scripts/validate_dev_deploy_config.sh
      - name: Configure AWS credentials
        with:
          role-to-assume: ${{ secrets.DEV_DEPLOY_ROLE_ARN }}
"""

    def _run_guard(self, workflow):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            workflow_dir = root / ".github" / "workflows"
            workflow_dir.mkdir(parents=True)
            (workflow_dir / "deploy-dev-lambda.yml").write_text(
                textwrap.dedent(workflow),
                encoding="utf-8",
            )
            return subprocess.run(
                ["bash", str(DEPLOY_GUARD)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_environment_variable_backed_workflow_passes(self):
        result = self._run_guard(self.VALID_WORKFLOW)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_missing_required_variable_reference_fails(self):
        workflow = self.VALID_WORKFLOW.replace(
            "AWS_REGION: ${{ vars.DEV_AWS_REGION }}",
            "AWS_REGION: us-east-1",
        )
        result = self._run_guard(workflow)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("vars.DEV_AWS_REGION", result.stdout + result.stderr)

    def test_hard_coded_ecr_account_fails(self):
        workflow = self.VALID_WORKFLOW.replace(
            "ECR_ACCOUNT_ID: ${{ vars.DEV_ECR_ACCOUNT_ID }}",
            "ECR_ACCOUNT_ID: 111111111111",
        )
        result = self._run_guard(workflow)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("vars.DEV_ECR_ACCOUNT_ID", result.stdout + result.stderr)

    def test_hard_coded_repository_fails(self):
        workflow = self.VALID_WORKFLOW.replace(
            "IMAGE_NAME: ${{ vars.DEV_ECR_REPOSITORY }}",
            "IMAGE_NAME: sample-worker",
        )
        result = self._run_guard(workflow)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("vars.DEV_ECR_REPOSITORY", result.stdout + result.stderr)

    def test_hard_coded_function_name_fails(self):
        workflow = self.VALID_WORKFLOW.replace(
            "FUNCTION_NAME: ${{ vars.DEV_LAMBDA_FUNCTION_NAME }}",
            "FUNCTION_NAME: dev-fn-sample",
        )
        result = self._run_guard(workflow)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("vars.DEV_LAMBDA_FUNCTION_NAME", result.stdout + result.stderr)

    def test_missing_fail_fast_validation_fails(self):
        workflow = self.VALID_WORKFLOW.replace(
            "      - name: Validate deployment configuration\n"
            "        run: ./scripts/validate_dev_deploy_config.sh\n",
            "",
        )
        result = self._run_guard(workflow)

        self.assertNotEqual(0, result.returncode)
        self.assertIn("validate deployment configuration", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
