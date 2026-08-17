from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

APP_NAME = "mdk-manager"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CACHE_DIR = CONFIG_DIR / "cache"
LOG_DIR = CONFIG_DIR / "logs"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "project_path": str(Path.home() / "MinecraftMods"),
    "auto_java": False,
    "cache_enabled": True,
    "cache_ttl_hours": 12,
    "download_retries": 3,
    "log_enabled": True,
}


def ensure_app_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    ensure_app_dirs()
    data = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except (OSError, json.JSONDecodeError):
            pass
    return data


def save_config(data: dict[str, Any]) -> None:
    ensure_app_dirs()
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_FILE)


def configure_logging(enabled: bool = True) -> logging.Logger:
    ensure_app_dirs()
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    if enabled:
        log_file = LOG_DIR / "mdk-manager.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    return logger


def cache_path(key: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in key)
    return CACHE_DIR / f"{safe}.json"


def cache_get(key: str, ttl_hours: int) -> Any | None:
    path = cache_path(key)
    if not path.exists():
        return None
    try:
        age = max(0.0, __import__("time").time() - path.stat().st_mtime)
        if age > max(0, ttl_hours) * 3600:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cache_set(key: str, value: Any) -> None:
    ensure_app_dirs()
    path = cache_path(key)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def clear_cache() -> int:
    ensure_app_dirs()
    count = 0
    for path in CACHE_DIR.glob("*.json"):
        try:
            path.unlink()
            count += 1
        except OSError:
            pass
    return count
