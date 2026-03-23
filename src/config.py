from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

env_path = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_path, case_sensitive=False, extra="ignore"
    )

    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    DB_ECHO: bool = False

    DB_HOST: str = ""
    DB_PORT: str = "5432"
    DB_USER: str = ""
    DB_PASS: str = ""
    DB_NAME: str = ""

    RABBITMQ_URL: str = "amqp://guest:guest@localhost:5672/"
    CART_SERVICE_URL: str = "http://localhost:8003"
    PRODUCT_SERVICE_URL: str = "http://localhost:8002"

    ORDER_PAYMENT_TIMEOUT_MS: int = 900_000

    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
