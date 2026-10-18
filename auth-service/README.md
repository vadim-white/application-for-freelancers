# Auth Service (auth-service)

Запуск локально (dev):
1. Скопируйте `.env.example` в `.env` и при необходимости отредактируйте.
2. Установите зависимости (нужен uv, Python 3.14 он поставит сам; `.venv` создаётся в папке сервиса):
   uv sync
3. Создайте таблицы миграциями (URL берётся из DATABASE_URL):
   uv run alembic upgrade head
4. Запустите сервис:
   uv run uvicorn app.main:app --reload --port 8001

Тесты запросов — см. ниже в инструкции.
