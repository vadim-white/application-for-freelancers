from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Без значения по умолчанию: без строки подключения сервис не стартует
    DATABASE_URL: str = Field(min_length=1)
    # Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ALGORITHM: str = "HS256"

    # task-service: проверка задачи при старте таймера (в Docker — имя контейнера)
    TASK_SERVICE_URL: str = "http://127.0.0.1:8002"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
