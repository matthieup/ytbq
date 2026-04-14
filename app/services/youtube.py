import yt_dlp
import os
from typing import List, Optional, Dict
from pathlib import Path
from app.models.schemas import VideoResult, VideoInfo
from app.config import VIDEO_QUALITY

_deno_path = Path(__file__).parent.parent.parent / ".deno" / "bin" / "deno"
if _deno_path.exists():
    os.environ["PATH"] = str(_deno_path.parent) + ":" + os.environ.get("PATH", "")


class YouTubeService:
    def __init__(self):
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "remote_components": ["ejs:github"],
        }

    def search_videos(self, query: str, limit: int = 10) -> List[VideoResult]:
        print(f"Searching for: {query} (limit: {limit})")
        search_opts = {
            **self.ydl_opts,
            "extract_flat": "in_playlist",
        }

        results = []
        try:
            with yt_dlp.YoutubeDL(search_opts) as ydl:
                search_results = ydl.extract_info(
                    f"ytsearch{limit}:{query}", download=False
                )

                if search_results and "entries" in search_results:
                    print(f"Found {len(search_results['entries'])} results")
                    for entry in search_results["entries"]:
                        if entry:
                            results.append(
                                VideoResult(
                                    id=entry.get("id", ""),
                                    title=entry.get("title", "Unknown"),
                                    thumbnail=self._get_best_thumbnail(entry),
                                    duration=self._format_duration(
                                        entry.get("duration")
                                    ),
                                    channel=entry.get("uploader")
                                    or entry.get("channel"),
                                    view_count=entry.get("view_count"),
                                )
                            )
        except Exception as e:
            print(f"Search error: {e}")

        return results

    def get_video_info(self, video_id: str) -> Optional[VideoInfo]:
        print(f"Getting video info for: {video_id}")
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )

                if info:
                    formats = info.get("formats", [])
                    stream_url = None
                    audio_url = None

                    for f in formats:
                        if f.get("vcodec") != "none" and f.get("acodec") != "none":
                            if not stream_url or f.get("height", 0) > 720:
                                stream_url = f.get("url")
                        elif f.get("acodec") != "none" and f.get("vcodec") == "none":
                            if not audio_url:
                                audio_url = f.get("url")

                    print(
                        f"Video info found: {info.get('title')}, stream_url: {stream_url[:50] if stream_url else 'None'}"
                    )
                    return VideoInfo(
                        id=video_id,
                        title=info.get("title", "Unknown"),
                        thumbnail=self._get_best_thumbnail(info),
                        duration=info.get("duration"),
                        channel=info.get("uploader") or info.get("channel"),
                        description=info.get("description", "")[:500]
                        if info.get("description")
                        else None,
                        stream_url=stream_url,
                        audio_url=audio_url,
                    )
        except Exception as e:
            print(f"Video info error: {e}")

        return None

    def get_stream_url(self, video_id: str, quality: int = None) -> Optional[dict]:
        print(f"Getting stream URL for video: {video_id}")
        target_quality = quality if quality else VIDEO_QUALITY
        print(f"Target quality: {target_quality}")
        try:
            opts = {
                **self.ydl_opts,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
                if not info:
                    return None

                formats = info.get("formats", [])
                video_url = None
                audio_url = None
                video_height = 0

                for f in formats:
                    height = f.get("height", 0) or 0
                    vcodec = f.get("vcodec", "none")
                    acodec = f.get("acodec", "none")
                    protocol = f.get("protocol", "")
                    url = f.get("url", "")

                    if protocol in ["m3u8", "m3u8_native"]:
                        continue

                    if vcodec != "none" and acodec != "none":
                        if height <= target_quality and height > video_height:
                            video_url = url
                            video_height = height
                            audio_url = None
                    elif vcodec != "none" and acodec == "none":
                        if height <= target_quality and height > video_height:
                            video_url = url
                            video_height = height
                    elif acodec != "none" and vcodec == "none":
                        if not audio_url and protocol not in ["m3u8", "m3u8_native"]:
                            audio_url = url

                print(f"Got video URL with height {video_height}p")
                return {
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "height": video_height,
                }
        except Exception as e:
            print(f"Stream URL error: {e}")

        return None

    def get_format_with_headers(
        self, video_id: str, quality: int = None
    ) -> Optional[Dict]:
        print(f"Getting format with headers for video: {video_id}")
        target_quality = quality if quality else VIDEO_QUALITY
        print(f"Target quality: {target_quality}")
        try:
            opts = {**self.ydl_opts}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )
                if not info:
                    return None

                formats = info.get("formats", [])
                candidates = []

                for f in formats:
                    height = f.get("height", 0) or 0
                    vcodec = f.get("vcodec", "none")
                    acodec = f.get("acodec", "none")
                    protocol = f.get("protocol", "")

                    if vcodec != "none" and acodec != "none":
                        if height <= target_quality:
                            is_hls = protocol in ["m3u8", "m3u8_native"]
                            candidates.append(
                                {
                                    "format": f,
                                    "height": height,
                                    "is_hls": is_hls,
                                }
                            )

                if candidates:
                    candidates.sort(key=lambda x: x["height"], reverse=True)

                    best_height = candidates[0]["height"]
                    same_height = [c for c in candidates if c["height"] == best_height]

                    best = None
                    for c in same_height:
                        if not c["is_hls"]:
                            best = c
                            break
                    if not best:
                        best = same_height[0]

                    f = best["format"]
                    return {
                        "url": f.get("url"),
                        "headers": f.get("http_headers", {}),
                        "height": best["height"],
                        "is_hls": best["is_hls"],
                    }

        except Exception as e:
            print(f"Format error: {e}")
        return None

    def _get_best_thumbnail(self, entry: dict) -> str:
        thumbnails = entry.get("thumbnails", [])
        if thumbnails:
            return thumbnails[-1].get("url", "")
        return entry.get(
            "thumbnail", f"https://i.ytimg.com/vi/{entry.get('id', '')}/hqdefault.jpg"
        )

    def _format_duration(self, seconds) -> Optional[str]:
        if seconds is None:
            return None
        try:
            seconds = int(seconds)
        except (ValueError, TypeError):
            return None
        minutes, secs = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"


youtube_service = YouTubeService()
