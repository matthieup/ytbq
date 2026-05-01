import json
import os
from pathlib import Path

_config_path = Path(__file__).parent.parent / "config.json"

with open(_config_path) as f:
    _config = json.load(f)

def _get_env(key, default=None):
    val = os.getenv(key)
    if val is not None:
        return val
    return default

def _get_int_env(key, default):
    val = os.getenv(key)
    if val is not None:
        try:
            return int(val)
        except ValueError:
            pass
    return default

def _get_bool_env(key, default):
    val = os.getenv(key)
    if val is not None:
        return val.lower() in ("true", "1", "yes", "on")
    return default

BASE_URL = _get_env("BASE_URL") or _config.get("base_url", "http://localhost:8000")
VIDEO_QUALITY = _get_int_env("VIDEO_QUALITY") if _get_env("VIDEO_QUALITY") else _config.get("video_quality", 1080)
ALLOW_MULTIPLE_VIDEOS = _get_bool_env("ALLOW_MULTIPLE_VIDEOS", _config.get("allow_multiple_videos", True)) if _get_env("ALLOW_MULTIPLE_VIDEOS") is not None else _config.get("allow_multiple_videos", True)
MULTIPLE_VIDEOS_LOCKED = _get_bool_env("MULTIPLE_VIDEOS_LOCKED", _config.get("multiple_videos_locked", False)) if _get_env("MULTIPLE_VIDEOS_LOCKED") is not None else _config.get("multiple_videos_locked", False)
AUTO_QUEUE_ENABLED = _get_bool_env("AUTO_QUEUE_ENABLED", _config.get("auto_queue_enabled", False)) if _get_env("AUTO_QUEUE_ENABLED") is not None else _config.get("auto_queue_enabled", False)
AUTO_QUEUE_LOCKED = _get_bool_env("AUTO_QUEUE_LOCKED", _config.get("auto_queue_locked", False)) if _get_env("AUTO_QUEUE_LOCKED") is not None else _config.get("auto_queue_locked", False)
LOGO_PATH = _get_env("LOGO_PATH") if _get_env("LOGO_PATH") else _config.get("logo_path", "")
MAX_DURATION_SECONDS = _get_int_env("MAX_DURATION_SECONDS") if _get_env("MAX_DURATION_SECONDS") else _config.get("max_duration_seconds", 600)


def reload_config():
    global \
        _config, \
        BASE_URL, \
        VIDEO_QUALITY, \
        ALLOW_MULTIPLE_VIDEOS, \
        MULTIPLE_VIDEOS_LOCKED, \
        AUTO_QUEUE_ENABLED, \
        AUTO_QUEUE_LOCKED, \
        LOGO_PATH, \
        MAX_DURATION_SECONDS
    with open(_config_path) as f:
        _config = json.load(f)
    BASE_URL = _get_env("BASE_URL") or _config.get("base_url", "http://localhost:8000")
    VIDEO_QUALITY = _get_int_env("VIDEO_QUALITY") if _get_env("VIDEO_QUALITY") else _config.get("video_quality", 1080)
    ALLOW_MULTIPLE_VIDEOS = _get_bool_env("ALLOW_MULTIPLE_VIDEOS", _config.get("allow_multiple_videos", True)) if _get_env("ALLOW_MULTIPLE_VIDEOS") is not None else _config.get("allow_multiple_videos", True)
    MULTIPLE_VIDEOS_LOCKED = _get_bool_env("MULTIPLE_VIDEOS_LOCKED", _config.get("multiple_videos_locked", False)) if _get_env("MULTIPLE_VIDEOS_LOCKED") is not None else _config.get("multiple_videos_locked", False)
    AUTO_QUEUE_ENABLED = _get_bool_env("AUTO_QUEUE_ENABLED", _config.get("auto_queue_enabled", False)) if _get_env("AUTO_QUEUE_ENABLED") is not None else _config.get("auto_queue_enabled", False)
    AUTO_QUEUE_LOCKED = _get_bool_env("AUTO_QUEUE_LOCKED", _config.get("auto_queue_locked", False)) if _get_env("AUTO_QUEUE_LOCKED") is not None else _config.get("auto_queue_locked", False)
    LOGO_PATH = _get_env("LOGO_PATH") if _get_env("LOGO_PATH") else _config.get("logo_path", "")
    MAX_DURATION_SECONDS = _get_int_env("MAX_DURATION_SECONDS") if _get_env("MAX_DURATION_SECONDS") else _config.get("max_duration_seconds", 600)


def get_config_dict():
    return {
        "base_url": BASE_URL,
        "video_quality": VIDEO_QUALITY,
        "allow_multiple_videos": ALLOW_MULTIPLE_VIDEOS,
        "multiple_videos_locked": MULTIPLE_VIDEOS_LOCKED,
        "auto_queue_enabled": AUTO_QUEUE_ENABLED,
        "auto_queue_locked": AUTO_QUEUE_LOCKED,
        "logo_path": LOGO_PATH,
        "max_duration_seconds": MAX_DURATION_SECONDS,
    }


def update_config(key: str, value):
    _config[key] = value
    with open(_config_path, "w") as f:
        json.dump(_config, f, indent=4)
    reload_config()
    return get_config_dict()


def set_base_url(base_url: str):
    return update_config("base_url", base_url)
