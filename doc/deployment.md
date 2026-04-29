# Deployment

This project uses separate workflows for dev deployment, production image release, and production Lambda deployment.

## Dev Deployment

Dev deployment runs automatically on push to `dev`.

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

## Production Image Release

Production image release runs automatically on push to `master`.

Before releasing or building the container image, the workflow validates the repository with:

- `uv sync --frozen --dev`
- Black
- Flake8
- `unittest`
- plaintext secret guard
- Lambda deployment workflow guardrails

The release workflow runs `python-semantic-release`.

Every successful master release workflow pushes these ECR image tags:

- `prod-<short_sha>`
- `sha-<short_sha>`

When `python-semantic-release` creates a release, the workflow also pushes:

- `vX.Y.Z`

The production image release workflow never deploys Lambda.

## Production Lambda Deploy

Production Lambda deployment is manual only.

The production deploy workflow uses `workflow_dispatch` and requires one input:

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
- Production Lambda deployment must always be manual.
- Deploy immutable tags only.
- Do not use `printenv`, a bare `env` command, or `set -x` in workflows.
- Avoid printing full Lambda function configuration in workflow logs.
