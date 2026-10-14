from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # адреса внутренних сервисов (в Docker используются имена контейнеров)
    AUTH_URL: str = os.getenv("AUTH_URL", "http://127.0.0.1:8001")
    TASK_URL: str = os.getenv("TASK_URL", "http://127.0.0.1:8002")
    TIME_URL: str = os.getenv("TIME_URL", "http://127.0.0.1:8003")

    # JWT validation — должен совпадать с auth-service SECRET_KEY & ALGORITHM
    SECRET_KEY: str = os.getenv("SECRET_KEY", "228")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

    # Gateway settings
    GATEWAY_PORT: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()
