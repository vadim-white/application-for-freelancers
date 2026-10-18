# Task Service (task-service)

Проекты и задачи; каждый пользователь видит только свои, администратор — все. Порт — 8002. OpenAPI: http://127.0.0.1:8002/docs

## Локальный запуск

1. Скопируйте `.env.example` в `.env`. `SECRET_KEY` должен совпадать во всех бэкенд-сервисах; `TIME_SERVICE_URL` — адрес time-service (по умолчанию в примере `http://127.0.0.1:8003`).
2. Установите зависимости (нужен uv, Python 3.14 он поставит сам; `.venv` создаётся в папке сервиса):
   ```bash
   uv sync
   ```
3. Создайте таблицы миграциями (повторять после обновления кода):
   ```bash
   uv run alembic upgrade head
   ```
4. Запустите сервис:
   ```bash
   uv run uvicorn app.main:app --reload --port 8002
   ```

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны. Тест миграций на PostgreSQL идёт, только если задана `TEST_POSTGRES_URL` — см. [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.
