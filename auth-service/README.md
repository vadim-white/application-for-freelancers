# Auth Service (auth-service)

Запуск локально (dev):
1. Скопируйте `.env.example` в `.env` и при необходимости отредактируйте.
2. Установите зависимости:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
3. Создайте таблицы миграциями (URL берётся из DATABASE_URL):
   alembic upgrade head
4. Запустите сервис:
   uvicorn app.main:app --reload --port 8001

Тесты запросов — см. ниже в инструкции.
