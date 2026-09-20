# Security Policy

## Reporting a Vulnerability

Do not disclose security vulnerabilities, credentials, tokens, OAuth payloads, encryption material, or real environment configuration in a public issue, pull request, discussion, log, screenshot, or code sample.

Prefer GitHub private vulnerability reporting for this repository when it is available from the repository Security tab.

If private vulnerability reporting is unavailable, open a minimal public issue that contains no sensitive technical details and only requests a private reporting channel. Do not include reproduction secrets, real account identifiers, provider payloads, or affected resource names in that issue.

## Sensitive Information

Treat the following as private operational data even when some individual values are not credentials by themselves:

- OAuth access tokens, refresh tokens, client secrets, and Notion integration tokens;
- token-encryption keys or encrypted token payloads;
- AWS account IDs, role ARNs, exact SSM parameter paths, DynamoDB table names, and environment-specific resource identifiers;
- real Notion database or page IDs;
- real Google Calendar IDs or event IDs;
- user UUIDs and production or development configuration copied from a live environment.

Use placeholders in examples and reports.

## Credential Exposure

If a credential or secret is accidentally published, do not rely on deleting or editing the GitHub content as remediation. Revoke or rotate the affected credential first, then remove the exposed value and assess whether repository history, workflow logs, releases, artifacts, or caches also contain it.

## Scope

Security reports should focus on vulnerabilities or credential exposure in this repository and its supported deployment/runtime behavior. General bugs and feature requests can use the normal public issue tracker when they do not require sensitive information.
