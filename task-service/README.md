# Task Service (task-service)

Запуск локально:
1. Установить зависимости (нужен uv, Python 3.14 он поставит сам; `.venv` создаётся в папке сервиса):
   uv sync

2. Скопировать пример .env:
   cp .env.example .env

3. Создать таблицы (миграции Alembic, повторять после обновления кода):
   uv run alembic upgrade head

4. Запустить:
   uv run uvicorn app.main:app --reload --port 8002

OpenAPI: http://127.0.0.1:8002/docs
