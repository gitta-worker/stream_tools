import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import app_config
import translation_server


class TranslationStateTests(unittest.TestCase):
    def test_publish_updates_latest_translation_and_version(self) -> None:
        state = translation_server.TranslationState()

        state.publish("こんにちは", "Hello")
        first = state.snapshot()
        state.publish("またね", "See you")
        second = state.snapshot()

        self.assertEqual(first["version"], 1)
        self.assertEqual(second["version"], 2)
        self.assertEqual(second["text_ja"], "またね")
        self.assertEqual(second["text_en"], "See you")
        self.assertEqual(second["status"], "ready")

    def test_snapshot_is_a_copy(self) -> None:
        state = translation_server.TranslationState()

        snapshot = state.snapshot()
        snapshot["status"] = "changed"

        self.assertEqual(state.snapshot()["status"], "starting")


class TranslationHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.original_config_path = translation_server.CONFIG_PATH
        cls.original_runtime_config = translation_server.runtime_config
        cls.config_path = Path(cls.temporary_directory.name) / "config.json"
        cls.config = copy.deepcopy(app_config.DEFAULT_CONFIG)
        cls.config["translation"]["deepl_auth_key"] = "test-secret"
        cls.config["apps"].update(
            {
                "obs_profile": "test",
                "onecomme_exe": "test.exe",
                "tanuesa_exe": "test.exe",
            }
        )
        app_config.save_config(cls.config_path, cls.config)
        translation_server.CONFIG_PATH = cls.config_path
        translation_server.runtime_config = cls.config
        cls.server = translation_server.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            translation_server.TranslationHandler,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        translation_server.CONFIG_PATH = cls.original_config_path
        translation_server.runtime_config = cls.original_runtime_config
        cls.temporary_directory.cleanup()

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_latest_translation_endpoint_returns_json(self) -> None:
        status, headers, body = self.request("/api/translation/latest")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertIn("version", json.loads(body))

    def test_root_serves_subtitle_page(self) -> None:
        status, headers, body = self.request("/")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(b"translation.js", body)

    def test_setup_page_is_available(self) -> None:
        status, headers, body = self.request("/setup")

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("初期設定".encode(), body)

    def test_config_api_does_not_return_secret(self) -> None:
        status, _, body = self.request("/api/config")
        payload = json.loads(body)

        self.assertEqual(status, 200)
        self.assertEqual(payload["translation"]["deepl_auth_key"], "")
        self.assertTrue(payload["translation"]["deepl_auth_key_configured"])

    def test_config_api_rejects_cross_origin_write(self) -> None:
        status, _, _ = self.request(
            "/api/config",
            method="POST",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://example.com",
            },
        )

        self.assertEqual(status, 403)

    def test_unknown_path_returns_not_found(self) -> None:
        status, _, _ = self.request("/not-found")

        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
