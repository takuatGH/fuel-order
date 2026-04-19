import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# Match the WhatsApp 24h messaging window — any retry after this is a genuine new message
MESSAGE_ID_TTL = 86400


async def is_already_seen(redis_client: redis.Redis, message_id: str) -> bool:
    """
    Check whether this WhatsApp message_id has already been processed.

    Returns True if seen before (caller should drop the message).
    Returns False and marks the ID as seen if this is the first time.
    Best-effort: on Redis failure logs a warning and returns False so the
    message is still processed rather than silently dropped.
    """
    key = f"msg_seen:{message_id}"
    try:
        inserted = await redis_client.set(key, "1", ex=MESSAGE_ID_TTL, nx=True)
        return inserted is None  # nx=True returns None when key already existed
    except Exception as e:
        logger.warning(f"idempotency check failed for {message_id}, processing anyway: {e}")
        return False
