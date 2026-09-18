from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


CONFIG_VERSION = 1

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "features": {
        "speech_recognition": True,
        "deepl_translation": True,
        "show_japanese": True,
        "show_english": True,
        "launch_onecomme": True,
        "launch_tanuesa": True,
        "launch_obs": True,
    },
    "speech": {
        "microphone_device_name": "",
        "microphone_device_index": None,
        "ambient_noise_duration": 3.0,
        "pause_threshold": 1.2,
        "non_speaking_duration": 0.8,
        "phrase_threshold": 0.2,
        "phrase_time_limit": 20,
    },
    "translation": {
        "deepl_auth_key": "",
        "deepl_api_url": "",
    },
    "server": {
        "host": "127.0.0.1",
        "port": 5000,
    },
    "apps": {
        "obs_exe": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        "obs_profile": "",
        "onecomme_exe": "",
        "tanuesa_exe": "",
    },
}


class ConfigError(ValueError):
    pass


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value


def load_config(path: Path) -> dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    if not path.exists():
        return config

    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"設定ファイルを読み込めません: {exc}") from exc
    if not isinstance(payload, dict):
        raise ConfigError("設定ファイルの最上位はJSONオブジェクトである必要があります")
    _deep_merge(config, payload)
    validate_config(config)
    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    validate_config(config)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    body = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary_path.write_text(body, encoding="utf-8")
        os.replace(temporary_path, path)
    except OSError as exc:
        raise ConfigError(f"設定ファイルを保存できません: {exc}") from exc


def merge_submitted_config(
    current: dict[str, Any], submitted: dict[str, Any]
) -> dict[str, Any]:
    if not isinstance(submitted, dict):
        raise ConfigError("送信された設定がJSONオブジェクトではありません")
    merged = copy.deepcopy(DEFAULT_CONFIG)
    _deep_merge(merged, submitted)

    submitted_key = str(
        submitted.get("translation", {}).get("deepl_auth_key", "")
    ).strip()
    if not submitted_key:
        merged["translation"]["deepl_auth_key"] = current["translation"][
            "deepl_auth_key"
        ]
    merged["version"] = CONFIG_VERSION
    validate_config(merged)
    return merged


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(config)
    auth_key = str(result["translation"].get("deepl_auth_key", "")).strip()
    result["translation"]["deepl_auth_key"] = ""
    result["translation"]["deepl_auth_key_configured"] = bool(auth_key)
    return result


def expand_path(value: str, app_dir: Path) -> Path:
    expanded = os.path.expandvars(value)
    path = Path(expanded)
    if not path.is_absolute():
        path = app_dir / path
    return path.resolve()


def _require_section(config: dict[str, Any], name: str) -> dict[str, Any]:
    section = config.get(name)
    if not isinstance(section, dict):
        raise ConfigError(f"{name} はJSONオブジェクトである必要があります")
    return section


def validate_config(config: dict[str, Any]) -> None:
    features = _require_section(config, "features")
    speech = _require_section(config, "speech")
    translation = _require_section(config, "translation")
    server = _require_section(config, "server")
    apps = _require_section(config, "apps")

    for name in DEFAULT_CONFIG["features"]:
        if not isinstance(features.get(name), bool):
            raise ConfigError(f"features.{name} はtrueまたはfalseで指定してください")

    numeric_rules = {
        "ambient_noise_duration": (0.0, 30.0),
        "pause_threshold": (0.1, 10.0),
        "non_speaking_duration": (0.0, 10.0),
        "phrase_threshold": (0.0, 10.0),
        "phrase_time_limit": (1, 300),
    }
    for name, (minimum, maximum) in numeric_rules.items():
        value = speech.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ConfigError(f"speech.{name} は数値で指定してください")
        if not minimum <= value <= maximum:
            raise ConfigError(
                f"speech.{name} は {minimum} から {maximum} の範囲で指定してください"
            )

    device_index = speech.get("microphone_device_index")
    if device_index is not None and (
        not isinstance(device_index, int) or isinstance(device_index, bool)
    ):
        raise ConfigError("speech.microphone_device_index は整数またはnullです")

    port = server.get("port")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ConfigError("server.port は1から65535の整数で指定してください")
    if server.get("host") not in {"127.0.0.1", "localhost"}:
        raise ConfigError("server.host は127.0.0.1またはlocalhostに限定されます")

    for section_name, section, names in (
        (
            "speech",
            speech,
            ("microphone_device_name",),
        ),
        (
            "translation",
            translation,
            ("deepl_auth_key", "deepl_api_url"),
        ),
        (
            "apps",
            apps,
            (
                "obs_exe",
                "obs_profile",
                "onecomme_exe",
                "tanuesa_exe",
            ),
        ),
    ):
        for name in names:
            if not isinstance(section.get(name), str):
                raise ConfigError(f"{section_name}.{name} は文字列で指定してください")

    required_app_paths = {
        "launch_obs": ("obs_exe", "obs_profile"),
        "launch_onecomme": ("onecomme_exe",),
        "launch_tanuesa": ("tanuesa_exe",),
    }
    for feature_name, path_names in required_app_paths.items():
        if features[feature_name]:
            for path_name in path_names:
                if not apps[path_name].strip():
                    raise ConfigError(
                        f"{feature_name}を使用する場合はapps.{path_name}が必要です"
                    )

    if features["deepl_translation"] and not translation["deepl_auth_key"].strip():
        raise ConfigError(
            "DeepL翻訳を使用する場合はtranslation.deepl_auth_keyが必要です"
        )
