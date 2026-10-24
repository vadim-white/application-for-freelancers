# Auth Service (auth-service)

Регистрация, вход и обновление токенов: пользователи, JWT access и refresh. Порт — 8001. OpenAPI: http://127.0.0.1:8001/docs

## Локальный запуск

1. Скопируйте `.env.example` в `.env`, при необходимости отредактируйте. `SECRET_KEY` должен совпадать во всех бэкенд-сервисах.
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
   uv run uvicorn app.main:app --reload --port 8001
   ```

Email без учёта регистра: `register` и `login` приводят адрес к нижнему регистру (`LowerEmailStr` в `app/schemas.py`), в базе он так и хранится. Адреса, сохранённые раньше, привела миграция `37998bcc3290`. Если в базе есть адреса, совпадающие без учёта регистра, миграция останавливается со списком и ничего не меняет: аккаунты нужно объединить или переименовать вручную. Её `downgrade` ничего не делает, исходный регистр не сохранён.

Проверка готовности: `GET http://127.0.0.1:8001/ready` — 200 `{"ready": true}`, если база доступна и схема не старше кода (ревизия в `alembic_version` равна head миграций или незнакома — новее); иначе 503 с причиной в `reason` (`schema not migrated`, `schema revision … is older than code …`, `database unavailable`). Эндпоинт вне `/api`, через gateway недоступен — его опрашивают healthcheck compose и readiness-проба Kubernetes. `GET /` — только «процесс отвечает» (liveness).

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны. Тесты миграций, `/ready` и таймаутов к базе на PostgreSQL идут, только если задана `TEST_POSTGRES_URL` — см. [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.
