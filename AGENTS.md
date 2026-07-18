# AGENTS.md

Project: **YTBQ — YouTube Jukebox**
A collaborative YouTube video queue for parties/gatherings. A host display plays videos while guests join via QR code from their phones, search YouTube, and add videos to a shared, real-time queue.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI + Uvicorn
- **Frontend**: Vanilla JS + Video.js (no build step)
- **Templates**: Jinja2 (`app/templates/`)
- **YouTube**: `yt-dlp` for search + stream/format extraction
- **DB**: SQLite (`ytbq.db`) via `sqlite3` (no ORM)
- **Realtime**: WebSockets
- **Tunnel**: `pyngrok` (auto-starts on server startup, sets `base_url`)
- **QR codes**: `qrcode[pil]`
- **Packaging**: `uv` (`uv.lock`, `pyproject.toml`); standalone binary via PyInstaller (`build.py`, `ytbq.spec`)

## Project Layout
```
run.py                  # Entry point — uvicorn on 0.0.0.0:8000
app/
  main.py              # FastAPI app, middleware (mobile redirect), ngrok startup/shutdown
  config.py            # Loads config.json + env vars; reload_config/update_config
  database.py          # SQLite schema, migrations, get_db
  routes/main.py       # All HTTP/WS endpoints (API + pages + HLS/segment proxy)
  services/
    queue.py           # QueueService — DB-backed queue, WS broadcast, play counts
    youtube.py         # YouTubeService — yt-dlp search, format/stream extraction, download/cache
    ngrok_tunnel.py    # pyngrok start/stop helpers
  models/schemas.py    # Pydantic models (VideoResult, VideoInfo, QueueItem, QueueState, PlayCount)
  templates/           # base.html, main.html, settings.html, guest/join.html
static/                # css/, js/{player,guest}.js, logo/, favicon.ico
tests/                 # pytest-asyncio; fixtures in conftest.py (temp_db via YTBQ_DB_PATH)
config.json            # Runtime config (also written by update_config)
build.py               # PyInstaller build script (--onefile / --onedir)
ytbq.spec              # PyInstaller spec
Dockerfile / docker-compose.yml
.env / .env.example    # Secrets (NGROK token) + config overrides
```

## Running
```bash
uv sync            # install deps
python run.py      # http://0.0.0.0:8000  (main display at /, guests at /join)
```
On startup the app opens an ngrok tunnel and overwrites `config.json.base_url` with the public URL (so QR codes point guests at the tunnel). Disable with `NGROK_AUTOSTART=0`.

## Configuration
Config is read from `config.json` and can be **overridden by env vars** (env wins). Keys:
- `base_url` / `BASE_URL` — URL guests use to join (set automatically by ngrok)
- `video_quality` / `VIDEO_QUALITY` — 360/480/720/1080/2160
- `allow_multiple_videos` / `ALLOW_MULTIPLE_VIDEOS` — whether a user may queue more than one video at once
- `multiple_videos_locked` / `MULTIPLE_VIDEOS_LOCKED` — lock the multi-add toggle in UI
- `auto_queue_enabled` / `AUTO_QUEUE_ENABLED` — auto-add a video from the same channel when the queue empties
- `auto_queue_locked` / `AUTO_QUEUE_LOCKED` — lock the auto-queue toggle
- `logo_path` / `LOGO_PATH` — logo shown above the QR code (empty = disabled)
- `max_duration_seconds` / `MAX_DURATION_SECONDS` — search duration cap (0 = unlimited)

Runtime-writable keys (via `POST /api/config`): `allow_multiple_videos`, `auto_queue_enabled`. `update_config()` persists back to `config.json`.

ngrok auth token env vars (checked in order): `NGROK_AUTHTOKEN`, `NGROK_AUTH_TOKEN`, `NGROK_TOKEN`.

## API Surface (app/routes/main.py)
- Pages: `GET /` (host display), `GET /join` (guest), `GET /settings`, `GET /qr` (QR PNG)
- Config: `GET /api/config`, `POST /api/config`
- Search: `GET /api/search?q=&limit=`
- Queue: `GET /api/queue`, `POST /api/queue`, `DELETE /api/queue/{index}`, `POST /api/queue/{index}/play`, `POST /api/queue/reorder`, `POST /api/queue/clear`, `POST /api/current/clear`
- Playback: `POST /api/next` (also triggers auto-queue when enabled), `GET /api/stream/{video_id}`, `GET /api/proxy/{video_id}` (cached file with HTTP Range support), HLS manifest rewrite + `GET /api/segment`
- Play counts: `GET /api/play-counts`, `GET /api/play-counts/{video_id}`
- WebSocket: `WS /ws` — server pushes queue state updates to all connected clients

## Middleware
`MobileRestrictMiddleware` (app/main.py) redirects mobile user-agents to `/join` unless the path is `/join`, `/api/*`, `/static/*`, or `/ws`. Keep new endpoints that mobile guests need within these allow-listed prefixes.

## Persistence (app/database.py)
- Tables: `queue_items`, `current_video` (singleton row id=1), `play_counts`
- `YTBQ_DB_PATH` env var overrides the DB path (used by tests)
- `init_db()` runs on import via `QueueService.__init__`; `migrate_from_json()` imports legacy `queue_state.json` / `play_counts.json` if the DB is empty
- Positions are renumbered after deletes (`_renumber_positions`)

## Video Streaming Strategy
- `YouTubeService` (app/services/youtube.py) wraps `yt-dlp`.
- `get_format_with_headers()` picks the highest progressive (combined audio+video) format ≤ target quality; falls back to HLS only if needed.
- `/api/proxy/{video_id}` downloads the full video to `video_cache/` (cached by video_id+quality, with TTL) and serves it with Range support for seeking.
- HLS manifests are rewritten so segment URLs route through `/api/segment` (cached headers in `_hls_cache` module-level dict in routes/main.py).
- `cookies.txt` at repo root (if present) is passed to yt-dlp for auth/age-gated content. **Do not commit `cookies.txt`.**

## Conventions
- No ORM; raw SQL via `sqlite3`. Use parameterized queries.
- Async service methods guard state mutation with `self._lock` (asyncio.Lock) and broadcast WS updates after mutations.
- Frontend is plain JS in `static/js/` — no bundler/transpiler.
- Tests use `pytest-asyncio` (`asyncio_mode = "auto"`); DB is isolated with a temp file via the `YTBQ_DB_PATH` env var + `temp_db` fixture.
- Lint/format: `ruff` (`.ruff_cache` present). Python version pinned via `.python-version`.

## Testing
```bash
uv run pytest          # run all tests
uv run pytest -q tests/test_queue_service.py
```
Only the queue service is covered. When adding queue/DB logic, add tests in `tests/test_queue_service.py` following the existing `async` fixture pattern.

## Building a Binary
```bash
python build.py --onefile --clean   # dist/ytbq/ytbq
python build.py                     # onedir
```
`build.py` ensures a default `config.json` exists and bundles `app/templates`, `static/`, and `config.json` into the PyInstaller artifact.

## Gotchas
- `config.json` is required at import time (`app/config.py` reads it on module load). The PyInstaller build and repo both ship one; don't delete it.
- The module-level `from app.config import ...` in `app/routes/main.py` captures values **at import time**. Use `get_config_dict()` / `update_config()` for live values rather than the imported constants for anything that can change at runtime.
- `_hls_cache` in routes/main.py is in-memory and per-process — not shared across workers (single-process uvicorn is the default).
- `cookies.txt`, `ytbq.db`, `video_cache/`, `.env`, and `dist/` are runtime/generated — leave them out of patches.
