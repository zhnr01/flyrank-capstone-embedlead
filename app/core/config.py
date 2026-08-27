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
