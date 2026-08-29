from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    project_name: str = "EmbedLead Widget Platform"
    environment: str = "local"
    secret_key: str = Field(
        default="local-development-only-change-me-32-bytes",
        min_length=32,
    )
    access_token_expire_minutes: int = Field(default=15, gt=0, le=1_440)
    backend_cors_origins: list[str] = Field(default_factory=list)
    max_submission_bytes: int = Field(default=8_192, gt=0, le=1_048_576)
    submission_rate_limit_per_ip: int = Field(default=5, gt=0, le=10_000)
    submission_rate_limit_per_widget: int = Field(default=30, gt=0, le=100_000)
    submission_rate_limit_window_seconds: int = Field(default=60, gt=0, le=3_600)
    login_rate_limit_per_ip: int = Field(default=10, gt=0, le=10_000)
    login_rate_limit_window_seconds: int = Field(default=300, gt=0, le=3_600)
    rate_limit_max_tracked_keys: int = Field(default=10_000, gt=0)
    redis_url: str = ""
    redis_socket_timeout_seconds: float = Field(default=0.25, gt=0, le=10)
    redis_connect_timeout_seconds: float = Field(default=0.25, gt=0, le=10)
    redis_health_check_interval_seconds: int = Field(default=30, ge=0, le=600)
    redis_health_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    geo_enrichment_enabled: bool = True
    geo_provider_a_enabled: bool = True
    geo_provider_b_enabled: bool = True
    geo_provider_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    outbox_max_attempts: int = Field(default=3, gt=0, le=20)
    outbox_batch_size: int = Field(default=20, gt=0, le=500)
    outbox_poll_seconds: float = Field(default=2.0, gt=0, le=60)
    notification_webhook_url: str = ""
    notification_webhook_secret: str = ""
    notification_webhook_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    widget_bundle_version: str = Field(default="v2", pattern=r"^v[0-9]+$")
    widget_config_cache_seconds: int = Field(default=60, gt=0, le=86_400)
    public_base_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    metrics_token: str = ""
    metrics_max_routes: int = Field(default=64, gt=0, le=10_000)
    postgres_server: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "embedlead"
    postgres_user: str = "embedlead"
    postgres_password: str = ""
    database_pool_timeout_seconds: int = 2
    database_connect_timeout_seconds: int = 2
    database_statement_timeout_ms: int = 2_000

    @model_validator(mode="after")
    def reject_development_secret_in_production(self) -> Settings:
        if self.environment == "production" and self.secret_key.startswith(
            "local-development-only-"
        ):
            raise ValueError("production requires a non-development secret key")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_server,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()
