"""fastapi application entry point.

this is the main application that wires together:
- api routers (webhooks, health)
- middleware (cors, logging)
- lifespan events (startup/shutdown)

run with:
    uvicorn src.main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings
from src.api import webhooks, health, admin


# configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """application lifespan handler."""
    settings = get_settings()
    logger.info(f"starting {settings.app_name}...")
    yield
    logger.info(f"shutting down {settings.app_name}...")


def create_app() -> FastAPI:
    """application factory."""
    settings = get_settings()
    
    app = FastAPI(
        title=settings.app_name,
        description="B2B fuel logistics platform - WhatsApp ordering system",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.debug else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(admin.router)
    
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )