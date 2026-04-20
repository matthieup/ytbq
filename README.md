# YTBQ - YouTube Jukebox

A collaborative YouTube video queue for parties, gatherings, or shared listening sessions.

## Features

- **Collaborative Queue**: Guests scan a QR code to join and add videos from their phones
- **Real-time Updates**: WebSocket-powered live queue synchronization
- **Video Streaming**: Direct YouTube streaming via yt-dlp with quality selection (4K to 360p)
- **Mobile-First Guest Interface**: Automatic mobile detection with optimized guest experience
- **Queue Management**: Drag-and-drop reordering, skip, remove, play next
- **Play Count Tracking**: See how many times each video has been played
- **Multi-add Control**: Optionally limit users to one video in queue at a time
- **Dark/Light Theme**: Toggle between themes

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **Frontend**: Vanilla JS + Video.js
- **YouTube Integration**: yt-dlp
- **QR Codes**: qrcode library

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd ytbq

# Install dependencies (using uv)
uv sync

# Or with pip
pip install -e .
```

## Configuration

Edit `config.json`:

```json
{
    "base_url": "http://192.168.1.108:8000",
    "video_quality": 1080,
    "allow_multiple_videos": true,
    "multiple_videos_locked": false
}
```

- `base_url`: The URL guests use to connect (update for your network)
- `video_quality`: Default quality (2160, 1080, 720, 480, 360)
- `allow_multiple_videos`: Whether users can queue multiple videos
- `multiple_videos_locked`: Prevent toggling the multi-add setting

## Running

```bash
python run.py
```

The server runs on `0.0.0.0:8000`.
On startup, the app also creates an ngrok tunnel and updates `config.json.base_url` to the ngrok public URL.

Environment variables:
- `NGROK_AUTOSTART` (default: `1`): set to `0` to disable automatic tunnel startup
- `NGROK_AUTHTOKEN` (optional): your ngrok auth token for stable limits/features

- **Main Display**: `http://localhost:8000/` - Shows the video player and queue
- **Guest Join**: `http://localhost:8000/join` - Mobile-friendly interface for guests

## How It Works

1. Open the main display on a TV/monitor
2. Guests scan the QR code or visit the join URL on their phones
3. Guests enter their name and search for YouTube videos
4. Selected videos are added to the shared queue
5. Videos play automatically in order, with real-time sync

## API Endpoints

- `GET /` - Main display interface
- `GET /join` - Guest mobile interface
- `GET /qr` - QR code PNG for joining
- `GET /api/search?q=query` - Search YouTube
- `GET /api/queue` - Get current queue state
- `POST /api/queue` - Add video to queue
- `DELETE /api/queue/{index}` - Remove from queue
- `POST /api/queue/{index}/play` - Play specific video
- `POST /api/queue/reorder` - Reorder queue
- `POST /api/next` - Get and play next video
- `GET /api/proxy/{video_id}` - Proxy video stream
- `WS /ws` - WebSocket for real-time updates
