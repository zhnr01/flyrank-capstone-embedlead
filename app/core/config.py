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
    postgres_server: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "embedlead"
    postgres_user: str = "embedlead"
    postgres_password: str = ""
    database_pool_timeout_seconds: int = 2
    database_connect_timeout_seconds: int = 2
    database_statement_timeout_ms: int = 2_000

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
