#!/usr/bin/env python3
"""Generate a Google OAuth refresh token for local .env.local setup.

This script is a developer setup helper only. It does not participate in
runtime sync and does not write token JSON files.
"""

import argparse
import getpass
import stat
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "openid",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
]


class RefreshTokenError(RuntimeError):
    """Raised when Google does not return a refresh token."""


def parse_scopes(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_SCOPES)
    scopes = [part.strip() for chunk in raw.split(",") for part in chunk.split() if part.strip()]
    if not scopes:
        raise ValueError("--scopes was provided but no valid scopes were found.")
    return scopes


def build_client_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": DEFAULT_TOKEN_URI,
            "redirect_uris": ["http://localhost"],
        }
    }


def build_env_snippet(client_id: str, client_secret: str, refresh_token: str) -> str:
    return "\n".join(
        [
            f"GOOGLE_CLIENT_ID={client_id}",
            f"GOOGLE_CLIENT_SECRET={client_secret}",
            f"GOOGLE_REFRESH_TOKEN={refresh_token}",
            f"GOOGLE_TOKEN_URI={DEFAULT_TOKEN_URI}",
            "",
        ]
    )


def require_refresh_token(credentials) -> str:
    refresh_token = getattr(credentials, "refresh_token", None)
    if refresh_token:
        return refresh_token
    raise RefreshTokenError(
        "Google did not return a refresh token.\n"
        "Likely causes:\n"
        "- OAuth consent was not forced.\n"
        "- This user previously granted access and Google did not return a new refresh token.\n"
        "- The OAuth client type is not Desktop app.\n"
        "- Requested scopes changed.\n"
        "Retry after revoking app access in your Google Account, or create a Desktop OAuth client and run again."
    )


def write_env_snippet(path: Path, snippet: str, force: bool = False) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists. Re-run with --force to overwrite.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snippet, encoding="utf-8")
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def run_oauth_flow(client_id: str, client_secret: str, scopes: list[str], no_browser: bool = False):
    flow = InstalledAppFlow.from_client_config(
        build_client_config(client_id, client_secret),
        scopes=scopes,
    )
    if no_browser and hasattr(flow, "run_console"):
        return flow.run_console(access_type="offline", prompt="consent", include_granted_scopes="true")
    if no_browser:
        raise RuntimeError(
            "The installed google-auth-oauthlib version does not support a console OAuth flow. "
            "Run without --no-browser on a machine with browser access."
        )
    return flow.run_local_server(
        port=0,
        open_browser=True,
        authorization_prompt_message="Open this URL to authorize local setup: {url}",
        success_message="Authorization complete. You may close this browser tab.",
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )


def parse_args(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Generate GOOGLE_REFRESH_TOKEN for local .env.local setup.")
    parser.add_argument("--client-id", help="Google OAuth Desktop client ID")
    parser.add_argument("--client-secret", help="Google OAuth Desktop client secret")
    parser.add_argument(
        "--scopes",
        help="Optional comma- or space-separated scopes. Defaults to the app's calendar/profile scopes.",
    )
    parser.add_argument("--output-env", help="Optional path to write the .env snippet")
    parser.add_argument("--force", action="store_true", help="Overwrite --output-env if it already exists")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Use console/manual OAuth flow if supported by the installed OAuth library",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    client_id = args.client_id or input("Google OAuth client ID: ").strip()
    client_secret = args.client_secret or getpass.getpass("Google OAuth client secret: ").strip()
    if not client_id:
        print("ERROR: Google OAuth client ID is required.", file=sys.stderr)
        return 1
    if not client_secret:
        print("ERROR: Google OAuth client secret is required.", file=sys.stderr)
        return 1

    try:
        scopes = parse_scopes(args.scopes)
        credentials = run_oauth_flow(client_id, client_secret, scopes, no_browser=args.no_browser)
        refresh_token = require_refresh_token(credentials)
        snippet = build_env_snippet(client_id, client_secret, refresh_token)
        if args.output_env:
            write_env_snippet(Path(args.output_env), snippet, force=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Do not commit this output. Paste it into .env.local only.")
    print()
    print(snippet, end="")
    if args.output_env:
        print(f"\nWrote env snippet to {args.output_env}. Do not commit that file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
