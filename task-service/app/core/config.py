from pydantic import Field
from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # Без значения по умолчанию: без строки подключения сервис не стартует
    DATABASE_URL: str = Field(min_length=1)

    # Адреса других сервисов (в Docker — имена контейнеров)
    TIME_SERVICE_URL: str = os.getenv("TIME_SERVICE_URL", "http://127.0.0.1:8003")

    # JWT. Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")

    class Config:
        env_file = ".env"

settings = Settings()
