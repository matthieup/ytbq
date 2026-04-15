import yt_dlp
import os
import asyncio
import time
from typing import List, Optional, Dict
from pathlib import Path
from app.models.schemas import VideoResult, VideoInfo
from app.config import VIDEO_QUALITY

CACHE_DIR = Path(__file__).parent.parent.parent / "video_cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_EXPIRY_SECONDS = 15 * 60  # 15 minutes

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

    async def download_video(self, video_id: str, quality: int = None) -> Optional[str]:
        target_quality = quality if quality else VIDEO_QUALITY
        cache_file = CACHE_DIR / f"{video_id}_{target_quality}.mp4"

        if cache_file.exists():
            print(f"Cache hit for {video_id} at {target_quality}p")
            return str(cache_file)

        print(f"Downloading {video_id} at {target_quality}p...")

        def _download():
            temp_file = CACHE_DIR / f"{video_id}_{target_quality}.temp.mp4"

            opts = {
                "format": f"bestvideo[height<={target_quality}]+bestaudio/best[height<={target_quality}]",
                "merge_output_format": "mp4",
                "outtmpl": str(temp_file),
                "quiet": False,
                "no_warnings": False,
                "overwrites": True,
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    result = ydl.extract_info(
                        f"https://www.youtube.com/watch?v={video_id}", download=True
                    )

                # Find the actual downloaded file (yt-dlp may add suffixes)
                downloaded_files = list(
                    CACHE_DIR.glob(f"{video_id}_{target_quality}.temp*.mp4")
                )

                if downloaded_files:
                    # Use the largest file (should be the merged one)
                    downloaded_file = max(
                        downloaded_files, key=lambda x: x.stat().st_size
                    )
                    downloaded_file.rename(cache_file)
                    print(f"Downloaded {video_id} to {cache_file}")
                    return str(cache_file)

            except Exception as e:
                print(f"Download error for {video_id}: {e}")
                # Clean up any partial files
                for f in CACHE_DIR.glob(f"{video_id}_{target_quality}.temp*"):
                    try:
                        f.unlink()
                    except:
                        pass
            return None

        return await asyncio.to_thread(_download)

        return await asyncio.to_thread(_download)

    def remove_cached_video(self, video_id: str, quality: int = None) -> bool:
        target_quality = quality if quality else VIDEO_QUALITY
        cache_file = CACHE_DIR / f"{video_id}_{target_quality}.mp4"
        if cache_file.exists():
            cache_file.unlink()
            print(f"Removed cached video: {cache_file}")
            return True
        return False

    def cleanup_old_cache(self) -> int:
        now = time.time()
        removed_count = 0

        for cache_file in CACHE_DIR.glob("*.mp4"):
            file_age = now - cache_file.stat().st_mtime

            if file_age > CACHE_EXPIRY_SECONDS:
                try:
                    cache_file.unlink()
                    print(
                        f"Removed expired cache: {cache_file.name} ({file_age / 60:.1f}m old)"
                    )
                    removed_count += 1
                except Exception as e:
                    print(f"Error removing {cache_file}: {e}")

        if removed_count > 0:
            print(f"Cache cleanup complete: removed {removed_count} files")

        return removed_count

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
                        is_hls = protocol in ["m3u8", "m3u8_native"]
                        if not is_hls and height <= target_quality:
                            candidates.append(
                                {
                                    "format": f,
                                    "height": height,
                                    "is_hls": False,
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
