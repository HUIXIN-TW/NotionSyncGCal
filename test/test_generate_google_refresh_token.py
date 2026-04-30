import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate-google-refresh-token.py"
spec = importlib.util.spec_from_file_location("generate_google_refresh_token", SCRIPT_PATH)
generate_google_refresh_token = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_google_refresh_token)


class GenerateGoogleRefreshTokenTests(unittest.TestCase):
    def test_default_scopes_are_app_scopes(self):
        self.assertEqual(
            generate_google_refresh_token.parse_scopes(None),
            [
                "https://www.googleapis.com/auth/calendar.events",
                "openid",
                "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/userinfo.email",
            ],
        )

    def test_env_snippet_does_not_include_access_token(self):
        snippet = generate_google_refresh_token.build_env_snippet(
            "client-id",
            "client-secret",
            "refresh-token",
        )
        self.assertIn("GOOGLE_CLIENT_ID=client-id", snippet)
        self.assertIn("GOOGLE_CLIENT_SECRET=client-secret", snippet)
        self.assertIn("GOOGLE_REFRESH_TOKEN=refresh-token", snippet)
        self.assertNotIn("access", snippet.lower())
        self.assertNotIn("expiry", snippet.lower())

    def test_missing_refresh_token_raises_clear_error(self):
        with self.assertRaises(generate_google_refresh_token.RefreshTokenError) as ctx:
            generate_google_refresh_token.require_refresh_token(SimpleNamespace(refresh_token=None))
        message = str(ctx.exception)
        self.assertIn("Google did not return a refresh token", message)
        self.assertIn("Desktop OAuth client", message)

    def test_output_file_refuses_overwrite_unless_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "google.env"
            path.write_text("existing=true\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                generate_google_refresh_token.write_env_snippet(path, "new=true\n", force=False)

            generate_google_refresh_token.write_env_snippet(path, "new=true\n", force=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "new=true\n")


if __name__ == "__main__":
    unittest.main()
