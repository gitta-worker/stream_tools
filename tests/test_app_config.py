import copy
import tempfile
import unittest
from pathlib import Path

import app_config


def valid_config() -> dict:
    config = copy.deepcopy(app_config.DEFAULT_CONFIG)
    config["translation"]["deepl_auth_key"] = "secret"
    config["apps"].update(
        {
            "obs_profile": "stream",
            "onecomme_exe": "onecomme.exe",
            "tanuesa_exe": "tanuesa.exe",
        }
    )
    return config


class AppConfigTests(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            expected = valid_config()

            app_config.save_config(path, expected)

            self.assertEqual(app_config.load_config(path), expected)

    def test_public_config_hides_deepl_key(self) -> None:
        result = app_config.public_config(valid_config())

        self.assertEqual(result["translation"]["deepl_auth_key"], "")
        self.assertTrue(result["translation"]["deepl_auth_key_configured"])

    def test_blank_submitted_key_preserves_existing_key(self) -> None:
        current = valid_config()
        submitted = copy.deepcopy(current)
        submitted["translation"]["deepl_auth_key"] = ""

        result = app_config.merge_submitted_config(current, submitted)

        self.assertEqual(result["translation"]["deepl_auth_key"], "secret")

    def test_disabled_apps_do_not_require_paths(self) -> None:
        config = valid_config()
        for name in (
            "launch_obs",
            "launch_onecomme",
            "launch_tanuesa",
        ):
            config["features"][name] = False
        config["apps"] = {name: "" for name in config["apps"]}

        app_config.validate_config(config)

    def test_translation_requires_key_when_enabled(self) -> None:
        config = valid_config()
        config["translation"]["deepl_auth_key"] = ""

        with self.assertRaises(app_config.ConfigError):
            app_config.validate_config(config)

    def test_enabled_custom_app_requires_executable(self) -> None:
        config = valid_config()
        config["custom_apps"] = [
            {
                "enabled": True,
                "name": "custom",
                "executable": "",
                "working_directory": "",
                "arguments": "",
            }
        ]

        with self.assertRaises(app_config.ConfigError):
            app_config.validate_config(config)

    def test_disabled_custom_app_may_be_incomplete(self) -> None:
        config = valid_config()
        config["custom_apps"] = [
            {
                "enabled": False,
                "name": "",
                "executable": "",
                "working_directory": "",
                "arguments": "",
            }
        ]

        app_config.validate_config(config)


if __name__ == "__main__":
    unittest.main()
