import pytest
import tempfile
import os
from datetime import datetime


@pytest.fixture
def temp_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    monkeypatch.setenv("YTBQ_DB_PATH", db_path)

    yield db_path

    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def sample_queue_item():
    from app.models.schemas import QueueItem

    return QueueItem(
        id="test_video_id",
        title="Test Video Title",
        thumbnail="https://example.com/thumb.jpg",
        duration="3:45",
        channel="Test Channel",
        added_at=datetime.now(),
        added_by="TestUser",
        user_id="user123",
        play_count=0,
    )


@pytest.fixture
def sample_queue_item2():
    from app.models.schemas import QueueItem

    return QueueItem(
        id="test_video_id_2",
        title="Second Test Video",
        thumbnail="https://example.com/thumb2.jpg",
        duration="5:30",
        channel="Another Channel",
        added_at=datetime.now(),
        added_by="OtherUser",
        user_id="user456",
        play_count=2,
    )
