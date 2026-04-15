import pytest
from app.services.queue import QueueService
from app.models.schemas import QueueItem
from datetime import datetime


@pytest.fixture
async def queue_service(temp_db):
    from app import database

    database.DATABASE_PATH = temp_db
    service = QueueService()
    return service


class TestQueueServiceAdd:
    @pytest.mark.asyncio
    async def test_add_to_queue_empty_queue(self, queue_service, sample_queue_item):
        length = await queue_service.add_to_queue(sample_queue_item)
        assert length == 1

        state = await queue_service.get_queue()
        assert len(state.items) == 1
        assert state.items[0].id == sample_queue_item.id

    @pytest.mark.asyncio
    async def test_add_to_queue_multiple_items(
        self, queue_service, sample_queue_item, sample_queue_item2
    ):
        await queue_service.add_to_queue(sample_queue_item)
        length = await queue_service.add_to_queue(sample_queue_item2)
        assert length == 2

        state = await queue_service.get_queue()
        assert len(state.items) == 2
        assert state.items[0].id == sample_queue_item.id
        assert state.items[1].id == sample_queue_item2.id


class TestQueueServiceRemove:
    @pytest.mark.asyncio
    async def test_remove_from_queue(
        self, queue_service, sample_queue_item, sample_queue_item2
    ):
        await queue_service.add_to_queue(sample_queue_item)
        await queue_service.add_to_queue(sample_queue_item2)

        result = await queue_service.remove_from_queue(0)
        assert result is True

        state = await queue_service.get_queue()
        assert len(state.items) == 1
        assert state.items[0].id == sample_queue_item2.id

    @pytest.mark.asyncio
    async def test_remove_from_queue_invalid_index(self, queue_service):
        result = await queue_service.remove_from_queue(99)
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_preserves_order(self, queue_service):
        for i in range(5):
            item = QueueItem(
                id=f"video_{i}",
                title=f"Video {i}",
                thumbnail="https://example.com/thumb.jpg",
                duration="1:00",
                channel="Channel",
                added_at=datetime.now(),
                added_by="User",
                user_id="user1",
                play_count=0,
            )
            await queue_service.add_to_queue(item)

        await queue_service.remove_from_queue(2)

        state = await queue_service.get_queue()
        assert len(state.items) == 4
        assert state.items[0].id == "video_0"
        assert state.items[1].id == "video_1"
        assert state.items[2].id == "video_3"
        assert state.items[3].id == "video_4"


class TestQueueServiceGetNext:
    @pytest.mark.asyncio
    async def test_get_next_video(self, queue_service, sample_queue_item):
        await queue_service.add_to_queue(sample_queue_item)

        next_video = await queue_service.get_next_video()
        assert next_video is not None
        assert next_video.id == sample_queue_item.id

        state = await queue_service.get_queue()
        assert len(state.items) == 0
        assert state.current is not None
        assert state.current.id == sample_queue_item.id

    @pytest.mark.asyncio
    async def test_get_next_video_empty_queue(self, queue_service):
        next_video = await queue_service.get_next_video()
        assert next_video is None

        state = await queue_service.get_queue()
        assert state.current is None

    @pytest.mark.asyncio
    async def test_get_next_video_debounced(self, queue_service, sample_queue_item):
        await queue_service.add_to_queue(sample_queue_item)

        result1 = await queue_service.get_next_video()
        result2 = await queue_service.get_next_video()

        assert result1 is not None
        assert result2 is None


class TestQueueServicePlayAtIndex:
    @pytest.mark.asyncio
    async def test_play_at_index(
        self, queue_service, sample_queue_item, sample_queue_item2
    ):
        await queue_service.add_to_queue(sample_queue_item)
        await queue_service.add_to_queue(sample_queue_item2)

        video = await queue_service.play_at_index(1)
        assert video is not None
        assert video.id == sample_queue_item2.id

        state = await queue_service.get_queue()
        assert len(state.items) == 1
        assert state.items[0].id == sample_queue_item.id
        assert state.current.id == sample_queue_item2.id

    @pytest.mark.asyncio
    async def test_play_at_invalid_index(self, queue_service):
        video = await queue_service.play_at_index(99)
        assert video is None


class TestQueueServiceClear:
    @pytest.mark.asyncio
    async def test_clear_queue(
        self, queue_service, sample_queue_item, sample_queue_item2
    ):
        await queue_service.add_to_queue(sample_queue_item)
        await queue_service.add_to_queue(sample_queue_item2)

        await queue_service.clear_queue()

        state = await queue_service.get_queue()
        assert len(state.items) == 0

    @pytest.mark.asyncio
    async def test_clear_current(self, queue_service, sample_queue_item):
        await queue_service.add_to_queue(sample_queue_item)
        await queue_service.get_next_video()

        await queue_service.clear_current()

        state = await queue_service.get_queue()
        assert state.current is None


class TestQueueServiceReorder:
    @pytest.mark.asyncio
    async def test_reorder_queue(self, queue_service):
        for i in range(3):
            item = QueueItem(
                id=f"video_{i}",
                title=f"Video {i}",
                thumbnail="https://example.com/thumb.jpg",
                duration="1:00",
                channel="Channel",
                added_at=datetime.now(),
                added_by="User",
                user_id="user1",
                play_count=0,
            )
            await queue_service.add_to_queue(item)

        result = await queue_service.reorder_queue(0, 2)
        assert result is True

        state = await queue_service.get_queue()
        assert state.items[0].id == "video_1"
        assert state.items[1].id == "video_2"
        assert state.items[2].id == "video_0"

    @pytest.mark.asyncio
    async def test_reorder_queue_invalid_indices(
        self, queue_service, sample_queue_item
    ):
        await queue_service.add_to_queue(sample_queue_item)

        result = await queue_service.reorder_queue(0, 99)
        assert result is False


class TestQueueServicePlayCount:
    @pytest.mark.asyncio
    async def test_play_count_incremented(self, queue_service, sample_queue_item):
        await queue_service.add_to_queue(sample_queue_item)

        video = await queue_service.get_next_video()
        assert video.play_count == 1

        state = await queue_service.get_queue()
        assert state.current.play_count == 1

    @pytest.mark.asyncio
    async def test_play_count_persists(self, queue_service, sample_queue_item):
        await queue_service.add_to_queue(sample_queue_item)
        await queue_service.get_next_video()

        await queue_service.add_to_queue(sample_queue_item)
        video = await queue_service.get_next_video()

        assert video.play_count == 2


class TestQueueServiceUserCheck:
    @pytest.mark.asyncio
    async def test_user_has_video_in_queue(self, queue_service, sample_queue_item):
        await queue_service.add_to_queue(sample_queue_item)

        has_video = await queue_service.user_has_video_in_queue("user123")
        assert has_video is True

        has_video = await queue_service.user_has_video_in_queue("nonexistent")
        assert has_video is False
