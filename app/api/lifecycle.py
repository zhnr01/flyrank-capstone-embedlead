import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.rate_limit_dependencies import close_rate_limiters
from app.core.db import engine
from app.core.redis_rate_limit import REDIS_FAILURES

logger = logging.getLogger(__name__)


def close_resources() -> None:
    try:
        close_rate_limiters()
    except REDIS_FAILURES:
        logger.warning("redis_close_failed")
    engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("application_startup")
    try:
        yield
    finally:
        close_resources()
        logger.info("application_shutdown")
