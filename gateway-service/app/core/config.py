from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # адреса внутренних сервисов (в Docker используются имена контейнеров)
    AUTH_URL: str = "http://127.0.0.1:8001"
    TASK_URL: str = "http://127.0.0.1:8002"
    TIME_URL: str = "http://127.0.0.1:8003"

    # JWT validation — должен совпадать с auth-service SECRET_KEY & ALGORITHM.
    # Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ALGORITHM: str = "HS256"

    # Origin'ы фронтенда, которым разрешён CORS, через запятую
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
