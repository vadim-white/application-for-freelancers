from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Без значения по умолчанию: без строки подключения сервис не стартует
    DATABASE_URL: str = Field(min_length=1)
    # Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ALGORITHM: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
