from sqlalchemy import create_engine

from app.core.config import settings

database_connect_args: dict[str, object] = {
    "connect_timeout": settings.database_connect_timeout_seconds,
    "options": f"-c statement_timeout={settings.database_statement_timeout_ms}",
}

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_timeout=settings.database_pool_timeout_seconds,
    connect_args=database_connect_args,
)
