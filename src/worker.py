"""
ARQ worker entry point.

Run alongside the web server:
    arq src.worker.WorkerSettings

The worker shares the same Redis instance as the web server. On startup it
creates a single DB session and WhatsApp client that are reused across tasks
within a job execution, then torn down on shutdown.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.services import WhatsAppClient
from src.tasks.dispatch import dispatch_order

logger = logging.getLogger(__name__)


async def startup(ctx: dict) -> None:
    settings = get_settings()

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    ctx["session"] = factory()
    ctx["engine"] = engine

    ctx["whatsapp"] = WhatsAppClient(
        phone_number_id=settings.whatsapp_phone_number_id,
        access_token=settings.whatsapp_access_token,
    )
    logger.info("ARQ worker started")


async def shutdown(ctx: dict) -> None:
    await ctx["session"].close()
    await ctx["engine"].dispose()
    logger.info("ARQ worker shut down")


class WorkerSettings:
    functions = [dispatch_order]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None   # set dynamically below
    max_tries = 3
    retry_delay = 5         # seconds between retries


# Resolve redis settings at import time so arq CLI picks them up
def _make_redis_settings():
    from arq.connections import RedisSettings
    settings = get_settings()
    url = settings.redis_url  # e.g. redis://localhost:6379/0
    # arq RedisSettings doesn't accept a URL directly — parse it
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/") or 0),
        password=parsed.password,
    )


WorkerSettings.redis_settings = _make_redis_settings()
