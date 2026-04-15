import json
from pathlib import Path

_config_path = Path(__file__).parent.parent / "config.json"

with open(_config_path) as f:
    _config = json.load(f)

BASE_URL = _config.get("base_url", "http://localhost:8000")
VIDEO_QUALITY = _config.get("video_quality", 1080)
ALLOW_MULTIPLE_VIDEOS = _config.get("allow_multiple_videos", True)
MULTIPLE_VIDEOS_LOCKED = _config.get("multiple_videos_locked", False)
AUTO_QUEUE_ENABLED = _config.get("auto_queue_enabled", False)
AUTO_QUEUE_LOCKED = _config.get("auto_queue_locked", False)


def reload_config():
    global \
        _config, \
        BASE_URL, \
        VIDEO_QUALITY, \
        ALLOW_MULTIPLE_VIDEOS, \
        MULTIPLE_VIDEOS_LOCKED, \
        AUTO_QUEUE_ENABLED, \
        AUTO_QUEUE_LOCKED
    with open(_config_path) as f:
        _config = json.load(f)
    BASE_URL = _config.get("base_url", "http://localhost:8000")
    VIDEO_QUALITY = _config.get("video_quality", 1080)
    ALLOW_MULTIPLE_VIDEOS = _config.get("allow_multiple_videos", True)
    MULTIPLE_VIDEOS_LOCKED = _config.get("multiple_videos_locked", False)
    AUTO_QUEUE_ENABLED = _config.get("auto_queue_enabled", False)
    AUTO_QUEUE_LOCKED = _config.get("auto_queue_locked", False)


def get_config_dict():
    return {
        "base_url": BASE_URL,
        "video_quality": VIDEO_QUALITY,
        "allow_multiple_videos": ALLOW_MULTIPLE_VIDEOS,
        "multiple_videos_locked": MULTIPLE_VIDEOS_LOCKED,
        "auto_queue_enabled": AUTO_QUEUE_ENABLED,
        "auto_queue_locked": AUTO_QUEUE_LOCKED,
    }


def update_config(key: str, value):
    _config[key] = value
    with open(_config_path, "w") as f:
        json.dump(_config, f, indent=4)
    reload_config()
    return get_config_dict()
