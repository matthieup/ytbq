import json
from pathlib import Path

_config_path = Path(__file__).parent.parent / "config.json"

with open(_config_path) as f:
    _config = json.load(f)

BASE_URL = _config.get("base_url", "http://localhost:8000")
VIDEO_QUALITY = _config.get("video_quality", 1080)
ALLOW_MULTIPLE_VIDEOS = _config.get("allow_multiple_videos", True)
MULTIPLE_VIDEOS_LOCKED = _config.get("multiple_videos_locked", False)
