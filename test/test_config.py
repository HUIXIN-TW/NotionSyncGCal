import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from config.config import generate_config, ConfigError  # noqa: E402


class TestGenerateConfigCloudMode(unittest.TestCase):
    def test_cloud_mode_returns_cloud_dict_with_uuid(self):
        uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.dict(os.environ, {"APP_MODE": "cloud"}):
            cfg = generate_config(uuid)
        self.assertEqual(cfg["mode"], "cloud")
        self.assertEqual(cfg["uuid"], uuid)

    def test_cloud_mode_contains_only_mode_and_uuid(self):
        uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.dict(os.environ, {"APP_MODE": "cloud"}):
            cfg = generate_config(uuid)
        self.assertSetEqual(set(cfg.keys()), {"mode", "uuid"})

    def test_cloud_mode_missing_uuid_raises(self):
        with patch.dict(os.environ, {"APP_MODE": "cloud"}):
            with self.assertRaises(ConfigError) as ctx:
                generate_config(user_uuid=None)
        self.assertIn("uuid is required", str(ctx.exception))

    def test_cloud_mode_empty_uuid_raises(self):
        with patch.dict(os.environ, {"APP_MODE": "cloud"}):
            with self.assertRaises(ConfigError):
                generate_config(user_uuid="")

    def test_cloud_mode_via_app_mode_argument(self):
        uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.dict(os.environ, {}, clear=False):
            cfg = generate_config(uuid, app_mode="cloud")
        self.assertEqual(cfg["mode"], "cloud")
        self.assertEqual(cfg["uuid"], uuid)

    def test_cloud_mode_does_not_contain_token_paths(self):
        uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.dict(os.environ, {"APP_MODE": "cloud"}):
            cfg = generate_config(uuid)
        for key in cfg:
            self.assertNotIn("path", key.lower(), msg=f"Unexpected path key in cloud config: {key}")


class TestGenerateConfigLocalMode(unittest.TestCase):
    def test_local_mode_returns_local_dict(self):
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config()
        self.assertEqual(cfg["mode"], "local")

    def test_local_mode_contains_notion_setting_path(self):
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config()
        self.assertIn("notion_setting_path", cfg)
        self.assertIsInstance(cfg["notion_setting_path"], Path)

    def test_local_mode_notion_setting_path_ends_correctly(self):
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config()
        self.assertTrue(
            str(cfg["notion_setting_path"]).endswith("config/local.notion-setting.json"),
            msg=f"Unexpected path: {cfg['notion_setting_path']}",
        )

    def test_local_mode_does_not_require_uuid(self):
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config(user_uuid=None)
        self.assertEqual(cfg["mode"], "local")

    def test_local_mode_uuid_ignored(self):
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config(user_uuid="some-uuid")
        self.assertNotIn("uuid", cfg)

    def test_local_mode_does_not_contain_token_dir_paths(self):
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config()
        for key, val in cfg.items():
            if isinstance(val, Path):
                self.assertNotIn("token/", str(val), msg=f"token/ path found in local config key '{key}': {val}")

    def test_local_mode_via_app_mode_argument(self):
        cfg = generate_config(app_mode="local")
        self.assertEqual(cfg["mode"], "local")


class TestGenerateConfigModeEnforcement(unittest.TestCase):
    def test_missing_app_mode_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError) as ctx:
                generate_config(user_uuid="some-uuid")
        self.assertIn("APP_MODE", str(ctx.exception))

    def test_unknown_app_mode_raises(self):
        with patch.dict(os.environ, {"APP_MODE": "staging"}):
            with self.assertRaises(ConfigError) as ctx:
                generate_config(user_uuid="some-uuid")
        self.assertIn("staging", str(ctx.exception))

    def test_legacy_local_string_raises(self):
        with patch.dict(os.environ, {"APP_MODE": "legacy_local"}):
            with self.assertRaises(ConfigError):
                generate_config()

    def test_serverless_string_raises(self):
        # "serverless" is no longer a valid mode; cloud must be used
        with patch.dict(os.environ, {"APP_MODE": "serverless"}):
            with self.assertRaises(ConfigError):
                generate_config(user_uuid="some-uuid")

    def test_app_mode_argument_overrides_env(self):
        # explicit app_mode= wins over APP_MODE env var
        uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        with patch.dict(os.environ, {"APP_MODE": "local"}):
            cfg = generate_config(user_uuid=uuid, app_mode="cloud")
        self.assertEqual(cfg["mode"], "cloud")
        self.assertEqual(cfg["uuid"], uuid)


if __name__ == "__main__":
    unittest.main()
