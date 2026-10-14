# Task Service (task-service)

Запуск локально:
1. Создать виртуальное окружение и установить зависимости:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Скопировать пример .env:
   cp .env.example .env

3. Создать таблицы (миграции Alembic, повторять после обновления кода):
   alembic upgrade head

4. Запустить:
   uvicorn app.main:app --reload --port 8002

OpenAPI: http://127.0.0.1:8002/docs
