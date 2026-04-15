import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from contextlib import contextmanager

DATABASE_PATH = Path(__file__).parent.parent / "ytbq.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS queue_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                thumbnail TEXT NOT NULL,
                duration TEXT,
                channel TEXT,
                added_at TEXT NOT NULL,
                added_by TEXT,
                user_id TEXT,
                play_count INTEGER DEFAULT 0,
                position INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS current_video (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                thumbnail TEXT NOT NULL,
                duration TEXT,
                channel TEXT,
                added_at TEXT NOT NULL,
                added_by TEXT,
                user_id TEXT,
                play_count INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS play_counts (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                count INTEGER DEFAULT 0,
                last_played TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_queue_position ON queue_items(position);
            CREATE INDEX IF NOT EXISTS idx_queue_video_id ON queue_items(video_id);
        """)
        conn.commit()


def migrate_from_json():
    queue_file = Path(__file__).parent.parent / "queue_state.json"
    play_counts_file = Path(__file__).parent.parent / "play_counts.json"

    with get_db() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM queue_items")
        if cursor.fetchone()[0] > 0:
            return

        if queue_file.exists():
            try:
                with open(queue_file) as f:
                    data = json.load(f)

                if data.get("current"):
                    current = data["current"]
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO current_video 
                        (id, video_id, title, thumbnail, duration, channel, added_at, added_by, user_id, play_count)
                        VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            current["id"],
                            current["title"],
                            current["thumbnail"],
                            current.get("duration"),
                            current.get("channel"),
                            current.get("added_at", datetime.now().isoformat()),
                            current.get("added_by"),
                            current.get("user_id"),
                            current.get("play_count", 0),
                        ),
                    )

                if data.get("queue"):
                    for i, item in enumerate(data["queue"]):
                        conn.execute(
                            """
                            INSERT INTO queue_items 
                            (video_id, title, thumbnail, duration, channel, added_at, added_by, user_id, play_count, position)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                item["id"],
                                item["title"],
                                item["thumbnail"],
                                item.get("duration"),
                                item.get("channel"),
                                item.get("added_at", datetime.now().isoformat()),
                                item.get("added_by"),
                                item.get("user_id"),
                                item.get("play_count", 0),
                                i,
                            ),
                        )

                conn.commit()
            except Exception as e:
                print(f"Migration error: {e}")

        if play_counts_file.exists():
            try:
                with open(play_counts_file) as f:
                    play_counts = json.load(f)

                for video_id, data in play_counts.items():
                    if isinstance(data, dict):
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO play_counts (video_id, title, count, last_played)
                            VALUES (?, ?, ?, ?)
                        """,
                            (
                                video_id,
                                data.get("title", ""),
                                data.get("count", 0),
                                data.get("last_played"),
                            ),
                        )

                conn.commit()
            except Exception as e:
                print(f"Play counts migration error: {e}")
