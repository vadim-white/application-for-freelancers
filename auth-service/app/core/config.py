from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Без значения по умолчанию: без строки подключения сервис не стартует
    DATABASE_URL: str = Field(min_length=1)
    # Без значения по умолчанию: без ключа сервис не стартует
    SECRET_KEY: str = Field(min_length=1)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    ALGORITHM: str = "HS256"
    # Тестовых пользователей создаёт команда python -m app.init_users,
    # и только при SEED_TEST_USERS=true
    SEED_TEST_USERS: bool = False

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
