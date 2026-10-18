import os

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # адреса внутренних сервисов (в Docker используются имена контейнеров)
    AUTH_URL: str = os.getenv("AUTH_URL", "http://127.0.0.1:8001")
    TASK_URL: str = os.getenv("TASK_URL", "http://127.0.0.1:8002")
    TIME_URL: str = os.getenv("TIME_URL", "http://127.0.0.1:8003")

    # JWT validation — должен совпадать с auth-service SECRET_KEY & ALGORITHM.
    # Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

    # Origin'ы фронтенда, которым разрешён CORS, через запятую
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Gateway settings
    GATEWAY_PORT: int = 8000


    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"

settings = Settings()
