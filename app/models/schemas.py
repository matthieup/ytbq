from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class VideoResult(BaseModel):
    id: str
    title: str
    thumbnail: str
    duration: Optional[str] = None
    channel: Optional[str] = None
    view_count: Optional[int] = None


class VideoInfo(BaseModel):
    id: str
    title: str
    thumbnail: str
    duration: Optional[int] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    stream_url: Optional[str] = None
    audio_url: Optional[str] = None


class QueueItem(BaseModel):
    id: str
    title: str
    thumbnail: str
    duration: Optional[str] = None
    channel: Optional[str] = None
    added_at: datetime = datetime.now()
    added_by: Optional[str] = None
    user_id: Optional[str] = None
    play_count: Optional[int] = None


class QueueState(BaseModel):
    current: Optional[QueueItem] = None
    items: List[QueueItem] = []


class PlayCount(BaseModel):
    video_id: str
    title: str
    count: int
    last_played: Optional[datetime] = None
