from __future__ import annotations

import argparse
import copy
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import certifi

from app_config import (
    ConfigError,
    DEFAULT_CONFIG,
    load_config,
    merge_submitted_config,
    public_config,
    save_config,
)


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
STATIC_FILES = {
    "/": (APP_DIR / "index.html", "text/html; charset=utf-8"),
    "/translation.js": (
        APP_DIR / "translation.js",
        "text/javascript; charset=utf-8",
    ),
    "/translation.css": (APP_DIR / "translation.css", "text/css; charset=utf-8"),
    "/setup": (APP_DIR / "setup.html", "text/html; charset=utf-8"),
    "/setup.js": (APP_DIR / "setup.js", "text/javascript; charset=utf-8"),
    "/setup.css": (APP_DIR / "setup.css", "text/css; charset=utf-8"),
}


class TranslationState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {
            "version": 0,
            "text_ja": "",
            "text_en": "",
            "updated_at": None,
            "status": "starting",
        }

    def update(self, **values: Any) -> None:
        with self._lock:
            self._data.update(values)

    def publish(self, text_ja: str, text_en: str) -> None:
        with self._lock:
            self._data.update(
                {
                    "version": self._data["version"] + 1,
                    "text_ja": text_ja,
                    "text_en": text_en,
                    "updated_at": time.time(),
                    "status": "ready",
                }
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._data)


state = TranslationState()
runtime_config: dict[str, Any] = DEFAULT_CONFIG


def deepl_api_url(config: dict[str, Any]) -> str:
    translation = config["translation"]
    configured_url = translation["deepl_api_url"].strip()
    if configured_url:
        return configured_url
    return (
        "https://api-free.deepl.com/v2/translate"
        if translation["deepl_auth_key"].strip().endswith(":fx")
        else "https://api.deepl.com/v2/translate"
    )


def translate_ja_to_en(text: str, config: dict[str, Any] | None = None) -> str:
    active_config = config or runtime_config
    auth_key = active_config["translation"]["deepl_auth_key"].strip()
    if not auth_key:
        raise RuntimeError("DeepL authentication key is not configured")

    request_data = urllib.parse.urlencode(
        {
            "text": text,
            "source_lang": "JA",
            "target_lang": "EN-US",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        deepl_api_url(active_config),
        data=request_data,
        headers={
            "Authorization": f"DeepL-Auth-Key {auth_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        request,
        timeout=20,
        context=ssl.create_default_context(cafile=certifi.where()),
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload["translations"][0]["text"])


def find_microphone_index(config: dict[str, Any], sr_module: Any) -> int | None:
    speech = config["speech"]
    configured_index = speech["microphone_device_index"]
    if configured_index is not None:
        return configured_index

    configured_name = speech["microphone_device_name"].strip()
    if not configured_name:
        return None

    candidates = [
        (index, name)
        for index, name in enumerate(sr_module.Microphone.list_microphone_names())
        if configured_name.casefold() in name.casefold()
    ]
    if not candidates:
        raise ValueError(f"Microphone was not found: {configured_name}")
    device_index, selected_name = candidates[0]
    print(
        f"[translation] Microphone: {selected_name} (index {device_index})",
        flush=True,
    )
    return device_index


def recognition_loop(config: dict[str, Any] | None = None) -> None:
    import speech_recognition as sr

    active_config = config or runtime_config
    speech = active_config["speech"]
    features = active_config["features"]
    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = speech["pause_threshold"]
    recognizer.non_speaking_duration = speech["non_speaking_duration"]
    recognizer.phrase_threshold = speech["phrase_threshold"]
    state.update(status="microphone_initializing")

    while True:
        try:
            device_index = find_microphone_index(active_config, sr)
            microphone = sr.Microphone(device_index=device_index)
            with microphone as source:
                duration = speech["ambient_noise_duration"]
                print(
                    "[translation] Adjusting for ambient noise "
                    f"({duration:.1f} seconds; keep silent)...",
                    flush=True,
                )
                recognizer.adjust_for_ambient_noise(source, duration=duration)
                state.update(status="listening")
                print(
                    "[translation] Listening (Japanese). "
                    f"energy_threshold={recognizer.energy_threshold:.1f}, "
                    f"pause_threshold={recognizer.pause_threshold:.1f}",
                    flush=True,
                )

                while True:
                    try:
                        audio = recognizer.listen(
                            source,
                            timeout=1,
                            phrase_time_limit=speech["phrase_time_limit"],
                        )
                    except sr.WaitTimeoutError:
                        continue

                    try:
                        text_ja = recognizer.recognize_google(
                            audio, language="ja-JP"
                        ).strip()
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError as exc:
                        state.update(status="speech_api_error")
                        print(f"[translation] Speech recognition error: {exc}", flush=True)
                        time.sleep(3)
                        continue

                    if not text_ja:
                        continue

                    print(f"[translation] JA: {text_ja}", flush=True)
                    text_en = ""
                    if features["deepl_translation"]:
                        state.update(status="translating")
                        try:
                            text_en = translate_ja_to_en(text_ja, active_config)
                        except (RuntimeError, KeyError, urllib.error.URLError) as exc:
                            state.update(status="translation_error")
                            print(f"[translation] DeepL error: {exc}", flush=True)
                            continue

                    state.publish(text_ja, text_en)
                    if text_en:
                        print(f"[translation] EN: {text_en}", flush=True)
        except (OSError, ValueError) as exc:
            state.update(status="microphone_error")
            print(f"[translation] Microphone error: {exc}", flush=True)
            time.sleep(5)


def microphone_names() -> list[dict[str, Any]]:
    import speech_recognition as sr

    return [
        {"index": index, "name": name}
        for index, name in enumerate(sr.Microphone.list_microphone_names())
    ]


class TranslationHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/translation/latest":
            snapshot = state.snapshot()
            snapshot.update(
                {
                    "show_japanese": runtime_config["features"]["show_japanese"],
                    "show_english": runtime_config["features"]["show_english"],
                }
            )
            self.send_json(snapshot, allow_origin=True)
            return
        if path == "/health":
            snapshot = state.snapshot()
            self.send_json({"ok": True, "status": snapshot["status"]}, allow_origin=True)
            return
        if path == "/api/config":
            try:
                config = load_config(CONFIG_PATH)
            except ConfigError as exc:
                print(f"[translation] Configuration warning: {exc}", flush=True)
                config = copy.deepcopy(DEFAULT_CONFIG)
            self.send_json(public_config(config))
            return
        if path == "/api/microphones":
            try:
                self.send_json({"microphones": microphone_names()})
            except (OSError, ImportError) as exc:
                self.send_json({"error": str(exc)}, status=500)
            return
        if path in STATIC_FILES:
            file_path, content_type = STATIC_FILES[path]
            self.send_file(file_path, content_type)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/config":
            self.send_error(404)
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json({"error": "Content-Type must be application/json"}, status=415)
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 1024 * 1024:
                raise ConfigError("設定データのサイズが不正です")
            request_body = self.rfile.read(content_length)
            if not self.is_same_origin_request():
                self.send_json({"error": "Cross-origin request was rejected"}, status=403)
                return
            submitted = json.loads(request_body.decode("utf-8"))
            try:
                current = load_config(CONFIG_PATH)
            except ConfigError:
                current = copy.deepcopy(DEFAULT_CONFIG)
            updated = merge_submitted_config(current, submitted)
            save_config(CONFIG_PATH, updated)
            self.send_json(
                {
                    "config": public_config(updated),
                    "restart_required": True,
                }
            )
        except (ConfigError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.send_json({"error": str(exc)}, status=400)

    def is_same_origin_request(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin == f"http://{self.headers.get('Host', '')}"

    def send_json(
        self,
        payload: dict[str, Any],
        *,
        status: int = 200,
        allow_origin: bool = False,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_body(
            body,
            "application/json; charset=utf-8",
            status=status,
            allow_origin=allow_origin,
        )

    def send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_body(body, content_type)

    def send_body(
        self,
        body: bytes,
        content_type: str,
        *,
        status: int = 200,
        allow_origin: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        if allow_origin:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_text: str, *args: Any) -> None:
        return


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Streaming translation subtitle server")
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="serve the setup UI without starting speech recognition",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="open the setup page in the default browser",
    )
    return parser.parse_args()


def main() -> None:
    global runtime_config

    args = parse_args()
    try:
        runtime_config = load_config(CONFIG_PATH)
    except ConfigError as exc:
        if not args.setup_only:
            raise SystemExit(f"[translation] Configuration error: {exc}") from exc
        print(f"[translation] Configuration warning: {exc}", flush=True)
        runtime_config = copy.deepcopy(DEFAULT_CONFIG)

    if not args.setup_only and not CONFIG_PATH.exists():
        raise SystemExit("[translation] config.json is missing. Run setup.bat first.")

    host = runtime_config["server"]["host"]
    port = runtime_config["server"]["port"]

    if args.setup_only:
        state.update(status="setup")
    elif runtime_config["features"]["speech_recognition"]:
        recognition_thread = threading.Thread(
            target=recognition_loop,
            args=(runtime_config,),
            name="speech-recognition",
            daemon=True,
        )
        recognition_thread.start()
    else:
        state.update(status="speech_disabled")

    server = ThreadingHTTPServer((host, port), TranslationHandler)
    print(f"[translation] Subtitle: http://{host}:{port}/", flush=True)
    print(f"[translation] Setup: http://{host}:{port}/setup", flush=True)
    if args.open_browser:
        threading.Timer(
            0.5,
            lambda: webbrowser.open(f"http://{host}:{port}/setup"),
        ).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
