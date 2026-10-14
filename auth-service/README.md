# Auth Service (auth-service)

Запуск локально (dev):
1. Скопируйте `.env.example` в `.env` и при необходимости отредактируйте.
2. Установите зависимости:
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
3. Инициализируйте БД (для sqlite используем create_all):
   python -c "from app.db import Base, engine; from app import models; Base.metadata.create_all(bind=engine)"
4. Запустите сервис:
   uvicorn app.main:app --reload --port 8001

Тесты запросов — см. ниже в инструкции.
