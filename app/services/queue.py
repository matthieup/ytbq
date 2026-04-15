from typing import List, Optional
from app.models.schemas import QueueItem, QueueState
from datetime import datetime
import asyncio
from app.database import get_db, init_db, migrate_from_json


class QueueService:
    def __init__(self):
        self._connections: List = []
        self._lock = asyncio.Lock()
        self._last_next_call = 0
        init_db()
        migrate_from_json()

    def _row_to_queue_item(self, row) -> QueueItem:
        return QueueItem(
            id=row["video_id"],
            title=row["title"],
            thumbnail=row["thumbnail"],
            duration=row["duration"],
            channel=row["channel"],
            added_at=datetime.fromisoformat(row["added_at"])
            if row["added_at"]
            else datetime.now(),
            added_by=row["added_by"],
            user_id=row["user_id"],
            play_count=row["play_count"],
        )

    def _delete_queue_item_by_id(self, conn, item_id: int):
        conn.execute("DELETE FROM queue_items WHERE id = ?", (item_id,))
        self._renumber_positions(conn)

    def _renumber_positions(self, conn):
        cursor = conn.execute("SELECT id FROM queue_items ORDER BY position")
        rows = cursor.fetchall()
        for i, row in enumerate(rows):
            conn.execute(
                "UPDATE queue_items SET position = ? WHERE id = ?", (i, row["id"])
            )

    def _set_current_video(self, conn, item: QueueItem):
        conn.execute(
            """
            INSERT OR REPLACE INTO current_video 
            (id, video_id, title, thumbnail, duration, channel, added_at, added_by, user_id, play_count)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.title,
                item.thumbnail,
                item.duration,
                item.channel,
                item.added_at.isoformat(),
                item.added_by,
                item.user_id,
                item.play_count or 0,
            ),
        )

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
            with get_db() as conn:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM queue_items"
                )
                position = cursor.fetchone()[0]

                conn.execute(
                    """
                    INSERT INTO queue_items 
                    (video_id, title, thumbnail, duration, channel, added_at, added_by, user_id, play_count, position)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        video.id,
                        video.title,
                        video.thumbnail,
                        video.duration,
                        video.channel,
                        video.added_at.isoformat(),
                        video.added_by,
                        video.user_id,
                        video.play_count or 0,
                        position,
                    ),
                )
                conn.commit()

                cursor = conn.execute("SELECT COUNT(*) FROM queue_items")
                queue_length = cursor.fetchone()[0]

        await self.broadcast_update()
        return queue_length

    async def remove_from_queue(self, index: int) -> bool:
        async with self._lock:
            with get_db() as conn:
                cursor = conn.execute(
                    "SELECT id FROM queue_items ORDER BY position LIMIT 1 OFFSET ?",
                    (index,),
                )
                row = cursor.fetchone()
                if not row:
                    return False

                self._delete_queue_item_by_id(conn, row["id"])
                conn.commit()

        await self.broadcast_update()
        return True

    async def get_next_video(self) -> Optional[QueueItem]:
        import time

        now = time.time()
        if now - self._last_next_call < 2:
            return None
        self._last_next_call = now

        async with self._lock:
            with get_db() as conn:
                cursor = conn.execute(
                    "SELECT * FROM queue_items ORDER BY position LIMIT 1"
                )
                row = cursor.fetchone()

                if not row:
                    conn.execute("DELETE FROM current_video WHERE id = 1")
                    conn.commit()
                    return None

                item = self._row_to_queue_item(row)
                self._delete_queue_item_by_id(conn, row["id"])
                self._set_current_video(conn, item)
                conn.commit()

        self._increment_play_count(item)
        await self.broadcast_update()
        return item

    async def clear_current(self):
        async with self._lock:
            with get_db() as conn:
                conn.execute("DELETE FROM current_video WHERE id = 1")
                conn.commit()

        await self.broadcast_update()

    async def play_at_index(self, index: int) -> Optional[QueueItem]:
        async with self._lock:
            with get_db() as conn:
                cursor = conn.execute(
                    "SELECT * FROM queue_items ORDER BY position LIMIT 1 OFFSET ?",
                    (index,),
                )
                row = cursor.fetchone()

                if not row:
                    return None

                item = self._row_to_queue_item(row)
                self._delete_queue_item_by_id(conn, row["id"])
                self._set_current_video(conn, item)
                conn.commit()

        self._increment_play_count(item)
        await self.broadcast_update()
        return item

    def _increment_play_count(self, video: QueueItem):
        with get_db() as conn:
            now = datetime.now().isoformat()

            cursor = conn.execute(
                "SELECT count FROM play_counts WHERE video_id = ?", (video.id,)
            )
            row = cursor.fetchone()

            if row:
                new_count = row["count"] + 1
                conn.execute(
                    """
                    UPDATE play_counts SET count = ?, last_played = ?, title = ?
                    WHERE video_id = ?
                """,
                    (new_count, now, video.title, video.id),
                )
            else:
                new_count = 1
                conn.execute(
                    """
                    INSERT INTO play_counts (video_id, title, count, last_played)
                    VALUES (?, ?, ?, ?)
                """,
                    (video.id, video.title, 1, now),
                )

            conn.execute(
                "UPDATE current_video SET play_count = ? WHERE id = 1", (new_count,)
            )
            conn.commit()

            video.play_count = new_count

    async def get_queue(self) -> QueueState:
        async with self._lock:
            return await self._get_state_internal()

    async def clear_queue(self):
        async with self._lock:
            with get_db() as conn:
                conn.execute("DELETE FROM queue_items")
                conn.commit()

        await self.broadcast_update()

    async def get_state(self) -> dict:
        async with self._lock:
            state = await self._get_state_internal()
        return state.model_dump(mode="json")

    async def _get_state_internal(self) -> QueueState:
        with get_db() as conn:
            cursor = conn.execute("SELECT * FROM current_video WHERE id = 1")
            current_row = cursor.fetchone()
            current = self._row_to_queue_item(current_row) if current_row else None

            cursor = conn.execute("SELECT * FROM queue_items ORDER BY position")
            rows = cursor.fetchall()
            items = [self._row_to_queue_item(row) for row in rows]

            return QueueState(current=current, items=items)

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
        with get_db() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM queue_items")
            return cursor.fetchone()[0]

    async def user_has_video_in_queue(self, user_id: str) -> bool:
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM queue_items WHERE user_id = ? LIMIT 1", (user_id,)
            )
            return cursor.fetchone() is not None

    async def reorder_queue(self, from_index: int, to_index: int) -> bool:
        async with self._lock:
            with get_db() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM queue_items")
                count = cursor.fetchone()[0]

                if (
                    from_index < 0
                    or from_index >= count
                    or to_index < 0
                    or to_index >= count
                ):
                    return False

                cursor = conn.execute("SELECT id FROM queue_items ORDER BY position")
                rows = cursor.fetchall()
                item_ids = [row["id"] for row in rows]

                item_id = item_ids.pop(from_index)
                item_ids.insert(to_index, item_id)

                for i, iid in enumerate(item_ids):
                    conn.execute(
                        "UPDATE queue_items SET position = ? WHERE id = ?", (i, iid)
                    )

                conn.commit()

        await self.broadcast_update()
        return True

    @property
    def _play_counts(self) -> dict:
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT video_id, title, count, last_played FROM play_counts"
            )
            result = {}
            for row in cursor.fetchall():
                result[row["video_id"]] = {
                    "video_id": row["video_id"],
                    "title": row["title"],
                    "count": row["count"],
                    "last_played": row["last_played"],
                }
            return result


queue_service = QueueService()
