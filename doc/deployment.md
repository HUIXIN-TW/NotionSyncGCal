# Deployment

This project uses separate workflows for CI validation, semantic release, dev deployment, and production Lambda deployment.

## CI

The CI workflow is `.github/workflows/ci-code-quality.yml`. It runs code quality checks, plaintext secret checks, and Lambda deployment workflow guardrails.

## Current Flow

- Dev push -> `.github/workflows/deploy-dev-lambda.yml` -> build/push dev image -> deploy dev Lambda.
- Master push -> `.github/workflows/release-semantic.yml` -> semantic-release only.
- Production image publish -> deferred.
- Production Lambda deploy -> `.github/workflows/disabled/deploy-prd-lambda.yml`, disabled until production infrastructure and IAM are ready.

## Release

Semantic release is repo-level, not environment-specific. There is no dev or production semantic-release workflow.

The release workflow is `.github/workflows/release-semantic.yml`. It runs automatically on push to `master`.

Before creating a release, the workflow validates the repository with:

- `uv sync --frozen --dev`
- Black
- Flake8
- `unittest`
- plaintext secret guard
- Lambda deployment workflow guardrails

The release workflow runs `python-semantic-release` only. It creates:

- Git tag
- GitHub Release

It does not commit version-file updates back to `master`, so it can run under PR-only branch protection.

The release workflow does not:

- configure AWS credentials
- log in to ECR
- build or push a container image
- deploy Lambda

## Release Version Source of Truth

Git tag and GitHub Release are the release version source of truth.

This repository is a Lambda application, not a published Python package. `pyproject.toml` `[project].version` is not used as deployment authority and may remain static while the project stays in this shape.

The `master` branch is protected and requires changes through pull requests. The release workflow must not push version bump commits directly to `master`, so semantic-release does not update `pyproject.toml` or `uv.lock` during release.

If this project later becomes a published Python package, revisit this decision and use either release pull requests or a controlled release bot bypass for version-file updates.

## Dev Deployment

The dev deployment workflow is `.github/workflows/deploy-dev-lambda.yml`. It runs automatically on push to `dev`.

Before building the container image, the workflow validates the repository with:

- `uv sync --frozen --dev`
- Black
- Flake8
- `unittest`
- plaintext secret guard
- Lambda deployment workflow guardrails

The dev workflow builds and pushes these ECR image tags:

- `dev`
- `dev-<short_sha>`
- `sha-<short_sha>`

The dev Lambda update uses the immutable `sha-<short_sha>` image tag. It updates only:

- `dev-fn-notion-sync-gcal`

## Production Image Publish

Production image publishing is deferred until production infrastructure, IAM, and cross-account ECR access are ready.

The future production image publish workflow must be manual only with `workflow_dispatch`. It must not deploy Lambda.

## Production Lambda Deploy

The production Lambda deployment workflow is `.github/workflows/disabled/deploy-prd-lambda.yml`. It is disabled until production infrastructure and IAM setup are ready.

When re-enabled, the production deploy workflow uses `workflow_dispatch` and requires one input:

- `image_tag`

The production Lambda function name comes from the protected GitHub Environment variable:

- `vars.PRD_FUNCTION_NAME`

The AWS role comes from:

- `secrets.PRD_DEPLOY_ROLE_ARN`

Allowed image tag formats:

- `vX.Y.Z`
- `sha-<short_sha>`
- `prod-<short_sha>`

Rejected mutable tags:

- `latest`
- `prod`
- `dev`

Before updating Lambda, the workflow verifies the requested image tag exists in ECR. Production deploys use this concurrency policy:

- `group: production-lambda-deploy`
- `cancel-in-progress: false`

## Required GitHub Setup

Required GitHub Environments:

- `dev`
- `production`

Production required reviewers are recommended.

Required secrets and variables:

- `DEV_DEPLOY_ROLE_ARN`
- `PRD_DEPLOY_ROLE_ARN`
- `PRD_FUNCTION_NAME`

`PRD_FUNCTION_NAME` must be configured as a protected GitHub Environment variable for the `production` environment.

## Safety Rules

- `master` push must never update Lambda.
- `master` push must never push an ECR image.
- Production image publishing must always be manual.
- Production Lambda deployment must always be manual.
- Deploy immutable tags only.
- Do not use `printenv`, a bare `env` command, or `set -x` in workflows.
- Avoid printing full Lambda function configuration in workflow logs.
