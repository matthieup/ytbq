from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from app.services.youtube import youtube_service
from app.services.queue import queue_service
from app.models.schemas import QueueItem
from app.config import (
    BASE_URL,
    VIDEO_QUALITY,
    ALLOW_MULTIPLE_VIDEOS,
    MULTIPLE_VIDEOS_LOCKED,
    AUTO_QUEUE_ENABLED,
    AUTO_QUEUE_LOCKED,
    get_config_dict,
    update_config,
)
from pydantic import BaseModel
import qrcode
import io
import httpx
from urllib.parse import urlencode
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_hls_cache: dict = {}


@router.get("/", response_class=HTMLResponse)
async def main_display(request: Request):
    join_url = f"{BASE_URL}/join"
    return templates.TemplateResponse(
        request=request,
        name="main.html",
        context={
            "join_url": join_url,
            "video_quality": VIDEO_QUALITY,
            "allow_multiple_videos": ALLOW_MULTIPLE_VIDEOS,
            "multiple_videos_locked": MULTIPLE_VIDEOS_LOCKED,
            "auto_queue_enabled": AUTO_QUEUE_ENABLED,
            "auto_queue_locked": AUTO_QUEUE_LOCKED,
        },
    )


@router.get("/join", response_class=HTMLResponse)
async def join_page(request: Request):
    return templates.TemplateResponse(request=request, name="guest/join.html")


@router.get("/qr")
async def get_qr_code():
    join_url = f"{BASE_URL}/join"

    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(join_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")


@router.get("/api/config")
async def get_config():
    return get_config_dict()


class ConfigUpdate(BaseModel):
    key: str
    value: bool


@router.post("/api/config")
async def set_config(config: ConfigUpdate):
    allowed_keys = ["allow_multiple_videos", "auto_queue_enabled"]
    if config.key not in allowed_keys:
        return {"success": False, "error": "Invalid config key"}
    return {"success": True, "config": update_config(config.key, config.value)}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await queue_service.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        await queue_service.disconnect(websocket)


@router.get("/api/search")
async def search_videos(q: str, limit: int = 10):
    results = youtube_service.search_videos(q, limit)
    return results


@router.get("/api/stream/{video_id}")
async def get_stream_url(video_id: str, quality: int = None):
    format_data = youtube_service.get_format_with_headers(video_id, quality)
    if format_data:
        return {
            "video_url": format_data.get("url"),
            "height": format_data.get("height"),
            "is_hls": format_data.get("is_hls", False),
        }
    return {"error": "Could not get stream URL"}


@router.get("/api/proxy/{video_id}")
async def proxy_stream(request: Request, video_id: str, quality: int = None):
    format_data = youtube_service.get_format_with_headers(video_id, quality)
    if not format_data:
        print(f"No format data for video: {video_id}")
        return Response(content=b"Could not get stream", status_code=404)

    url = format_data["url"]
    headers = format_data.get("headers", {})
    headers.pop("Sec-Fetch-Mode", None)

    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    is_hls = format_data.get("is_hls", False)
    print(
        f"Proxy stream for {video_id}: is_hls={is_hls}, height={format_data.get('height')}"
    )

    if not is_hls:

        async def stream_generator():
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type="video/mp4",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    cache_key = f"{video_id}:{quality}"
    _hls_cache[cache_key] = {"url": url, "headers": headers}

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        manifest = response.text

    base_url = str(request.base_url).rstrip("/")

    lines = manifest.split("\n")
    rewritten_lines = []
    manifest_base_url = url.rsplit("/", 1)[0] if "/" in url else url

    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            if line.startswith("http"):
                segment_url = line
            else:
                segment_url = f"{manifest_base_url}/{line}"

            params = urlencode({"url": segment_url, "cache_key": cache_key})
            rewritten_lines.append(f"{base_url}/api/segment?{params}")
        else:
            rewritten_lines.append(line)

    rewritten_manifest = "\n".join(rewritten_lines)
    print(
        f"HLS manifest rewritten for {video_id}, {len([l for l in lines if l and not l.startswith('#')])} segments"
    )
    return Response(
        content=rewritten_manifest,
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*"},
    )

    if not is_hls:

        async def stream_generator():
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        yield chunk

        return StreamingResponse(
            stream_generator(),
            media_type="video/mp4",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    cache_key = f"{video_id}:{quality}"
    _hls_cache[cache_key] = {"url": url, "headers": headers}

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        manifest = response.text

    lines = manifest.split("\n")
    rewritten_lines = []
    base_url = url.rsplit("/", 1)[0] if "/" in url else url

    for line in lines:
        line = line.strip()
        if line and not line.startswith("#"):
            if line.startswith("http"):
                segment_url = line
            else:
                segment_url = f"{base_url}/{line}"

            params = urlencode({"url": segment_url, "cache_key": cache_key})
            rewritten_lines.append(f"/api/segment?{params}")
        else:
            rewritten_lines.append(line)

    rewritten_manifest = "\n".join(rewritten_lines)
    print(
        f"HLS manifest rewritten for {video_id}, {len([l for l in lines if l and not l.startswith('#')])} segments"
    )
    return Response(
        content=rewritten_manifest,
        media_type="application/vnd.apple.mpegurl",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.get("/api/segment")
async def proxy_segment(url: str, cache_key: str = None):
    headers = {}
    if cache_key and cache_key in _hls_cache:
        headers = _hls_cache[cache_key].get("headers", {}).copy()
        headers.pop("Sec-Fetch-Mode", None)

    async def stream_generator():
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                async with client.stream("GET", url, headers=headers) as response:
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        yield chunk
        except Exception as e:
            print(f"Segment stream error: {e}")
            raise

    return StreamingResponse(
        stream_generator(),
        media_type="video/MP2T",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@router.post("/api/queue")
async def add_to_queue(item: QueueItem):
    if not ALLOW_MULTIPLE_VIDEOS and item.user_id:
        has_video = await queue_service.user_has_video_in_queue(item.user_id)
        if has_video:
            return {
                "success": False,
                "error": "Wait for your queued song to play first :)",
            }
    await queue_service.add_to_queue(item)
    return {"success": True, "position": queue_service.get_queue_length()}


@router.delete("/api/queue/{index}")
async def remove_from_queue(index: int):
    success = await queue_service.remove_from_queue(index)
    return {"success": success}


@router.post("/api/queue/{index}/play")
async def play_queue_item(index: int):
    video = await queue_service.play_at_index(index)
    if video:
        result = {"video": video.model_dump(mode="json")}
        return result
    return {"video": None}


@router.post("/api/next")
async def get_next_video():
    video = await queue_service.get_next_video()
    if video:
        return {"video": video.model_dump(mode="json")}

    from app.config import AUTO_QUEUE_ENABLED

    if AUTO_QUEUE_ENABLED:
        last_video = queue_service.get_last_played_video()
        if last_video and last_video.get("channel"):
            auto_video = await auto_queue_from_artist(
                last_video["channel"], last_video["video_id"]
            )
            if auto_video:
                return {"video": auto_video.model_dump(mode="json")}

    return {"video": None}


async def auto_queue_from_artist(channel: str, exclude_video_id: str = None):
    import random
    from app.services.youtube import youtube_service

    search_query = f"{channel} - official"
    results = youtube_service.search_videos(search_query, limit=10)

    if not results:
        return None

    valid_results = [r for r in results if r.id != exclude_video_id]
    if not valid_results:
        valid_results = results

    chosen = random.choice(valid_results)

    item = QueueItem(
        id=chosen.id,
        title=chosen.title,
        thumbnail=chosen.thumbnail,
        duration=chosen.duration,
        channel=chosen.channel,
        added_at=datetime.now(),
        added_by="Auto-Queue",
        user_id="auto_queue",
        play_count=0,
    )

    await queue_service.set_current_video(item)
    await queue_service.broadcast_update()

    return item


@router.post("/api/current/clear")
async def clear_current():
    await queue_service.clear_current()
    return {"success": True}


@router.post("/api/queue/clear")
async def clear_queue():
    await queue_service.clear_queue()
    return {"success": True}


class ReorderRequest(BaseModel):
    from_index: int
    to_index: int


@router.post("/api/queue/reorder")
async def reorder_queue(request: ReorderRequest):
    success = await queue_service.reorder_queue(request.from_index, request.to_index)
    return {"success": success}


@router.get("/api/queue")
async def get_queue():
    state = await queue_service.get_state()
    return state


@router.get("/api/play-counts")
async def get_play_counts():
    return queue_service._play_counts


@router.get("/api/play-counts/{video_id}")
async def get_video_play_count(video_id: str):
    count_data = queue_service._play_counts.get(video_id)
    if count_data:
        return count_data
    return {"video_id": video_id, "count": 0}
