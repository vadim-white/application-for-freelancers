from pydantic import Field
from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # Без значения по умолчанию: без строки подключения сервис не стартует
    DATABASE_URL: str = Field(min_length=1)
    # Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    # Тестовые пользователи создаются при старте только при SEED_TEST_USERS=true
    SEED_TEST_USERS: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
