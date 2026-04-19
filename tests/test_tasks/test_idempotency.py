import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.tasks.idempotency import is_already_seen, MESSAGE_ID_TTL


def make_redis(set_return=True):
    """set_return=True means nx insert succeeded (key was new)."""
    r = AsyncMock()
    r.set = AsyncMock(return_value=True if set_return else None)
    return r


async def test_first_call_returns_false_and_marks_seen():
    redis_mock = make_redis(set_return=True)  # nx succeeded → key was new
    result = await is_already_seen(redis_mock, "wamid.abc123")
    assert result is False
    redis_mock.set.assert_awaited_once_with(
        "msg_seen:wamid.abc123", "1", ex=MESSAGE_ID_TTL, nx=True
    )


async def test_second_call_returns_true():
    redis_mock = make_redis(set_return=False)  # nx failed → key already existed
    result = await is_already_seen(redis_mock, "wamid.abc123")
    assert result is True


async def test_redis_failure_returns_false_and_logs_warning():
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(side_effect=Exception("connection refused"))
    result = await is_already_seen(redis_mock, "wamid.abc123")
    # Should fail open — process the message rather than silently drop it
    assert result is False


async def test_different_message_ids_are_independent():
    redis_mock = make_redis(set_return=True)
    r1 = await is_already_seen(redis_mock, "wamid.aaa")
    r2 = await is_already_seen(redis_mock, "wamid.bbb")
    assert r1 is False
    assert r2 is False
    assert redis_mock.set.await_count == 2
