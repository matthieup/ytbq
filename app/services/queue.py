from typing import List, Optional
from app.models.schemas import QueueItem, QueueState, PlayCount
from datetime import datetime
import asyncio
import json
import os
import time


class QueueService:
    QUEUE_FILE = "queue_state.json"
    PLAY_COUNTS_FILE = "play_counts.json"

    def __init__(self):
        self._queue: List[QueueItem] = []
        self._current: Optional[QueueItem] = None
        self._connections: List = []
        self._lock = asyncio.Lock()
        self._play_counts: dict = {}
        self._last_next_call = 0
        self._load_state()
        self._load_play_counts()

    def _load_state(self):
        if os.path.exists(self.QUEUE_FILE):
            try:
                with open(self.QUEUE_FILE, "r") as f:
                    data = json.load(f)
                    if data.get("queue"):
                        self._queue = [QueueItem(**item) for item in data["queue"]]
                    if data.get("current"):
                        self._current = QueueItem(**data["current"])
            except Exception as e:
                pass

    def _load_play_counts(self):
        if os.path.exists(self.PLAY_COUNTS_FILE):
            try:
                with open(self.PLAY_COUNTS_FILE, "r") as f:
                    self._play_counts = json.load(f)
            except Exception as e:
                self._play_counts = {}

    def _save_play_counts(self):
        try:
            with open(self.PLAY_COUNTS_FILE, "w") as f:
                json.dump(self._play_counts, f, default=str)
        except Exception as e:
            pass

    def _save_state(self):
        try:
            data = {
                "queue": [item.model_dump(mode="json") for item in self._queue],
                "current": self._current.model_dump(mode="json")
                if self._current
                else None,
            }
            with open(self.QUEUE_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            pass

    async def connect(self, websocket):
        async with self._lock:
            self._connections.append(websocket)
        await self.send_state(websocket)

    async def disconnect(self, websocket):
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def add_to_queue(self, video: QueueItem) -> int:
        async with self._lock:
            self._queue.append(video)
            position = len(self._queue)
        self._save_state()
        await self.broadcast_update()
        return position

    async def remove_from_queue(self, index: int) -> bool:
        async with self._lock:
            if 0 <= index < len(self._queue):
                self._queue.pop(index)
                result = True
            else:
                result = False
        if result:
            self._save_state()
            await self.broadcast_update()
        return result

    async def get_next_video(self) -> Optional[QueueItem]:
        now = time.time()
        if now - self._last_next_call < 2:
            return None
        self._last_next_call = now

        async with self._lock:
            if self._queue:
                self._current = self._queue.pop(0)
                result = self._current
            else:
                self._current = None
                result = None
        if result:
            self._increment_play_count(result)
        self._save_state()
        await self.broadcast_update()
        return result

    async def clear_current(self):
        async with self._lock:
            self._current = None
        self._save_state()
        await self.broadcast_update()

    async def play_at_index(self, index: int) -> Optional[QueueItem]:
        async with self._lock:
            if 0 <= index < len(self._queue):
                self._current = self._queue.pop(index)
                result = self._current
            else:
                result = None
        if result:
            self._increment_play_count(result)
            self._save_state()
            await self.broadcast_update()
        return result

    def _increment_play_count(self, video: QueueItem):
        video_id = video.id
        if video_id not in self._play_counts:
            self._play_counts[video_id] = {
                "video_id": video_id,
                "title": video.title,
                "count": 0,
                "last_played": None,
            }
        self._play_counts[video_id]["count"] += 1
        self._play_counts[video_id]["last_played"] = datetime.now().isoformat()
        video.play_count = self._play_counts[video_id]["count"]
        self._save_play_counts()

    async def get_queue(self) -> QueueState:
        async with self._lock:
            return QueueState(current=self._current, items=list(self._queue))

    async def clear_queue(self):
        async with self._lock:
            self._queue = []
        await self.broadcast_update()

    async def get_state(self) -> dict:
        async with self._lock:
            state = QueueState(current=self._current, items=list(self._queue))
        return state.model_dump(mode="json")

    async def send_state(self, websocket):
        try:
            state = await self.get_state()
            await websocket.send_json({"type": "state", "data": state})
        except Exception as e:
            pass

    async def broadcast_update(self):
        state = await self.get_state()
        message = {"type": "state", "data": state}
        disconnected = []
        for i, ws in enumerate(self._connections):
            try:
                await ws.send_json(message)
            except Exception as e:
                disconnected.append(ws)

        for ws in disconnected:
            if ws in self._connections:
                self._connections.remove(ws)

    def get_queue_length(self) -> int:
        return len(self._queue)

    async def user_has_video_in_queue(self, user_id: str) -> bool:
        async with self._lock:
            for item in self._queue:
                if item.user_id == user_id:
                    return True
            return False

    async def reorder_queue(self, from_index: int, to_index: int) -> bool:
        async with self._lock:
            if 0 <= from_index < len(self._queue) and 0 <= to_index < len(self._queue):
                item = self._queue.pop(from_index)
                self._queue.insert(to_index, item)
                result = True
            else:
                result = False
        if result:
            self._save_state()
            await self.broadcast_update()
        return result


queue_service = QueueService()
