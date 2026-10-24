# Task Service (task-service)

Проекты и задачи; каждый пользователь видит только свои, администратор — все. Порт — 8002. OpenAPI: http://127.0.0.1:8002/docs

## Списки

`GET /api/tasks/projects` и `GET /api/tasks/tasks` отдают конверт `{items, total, limit, offset}` (`limit` 1–200, по умолчанию 50; `total` — с теми же фильтрами). Белые списки `sort` и фильтры — в [«API» корневого README](../README.md#api). Порядок одинаков на SQLite и PostgreSQL: `status` сортируется выражением `CASE` в порядке объявления `TaskStatus` (иначе SQLite сортирует по алфавиту), `NULL` — `NULLS LAST` в обе стороны, `updated_at` — `coalesce(updated_at, created_at)` (до первой правки `updated_at` пуст), `title` и `name` — по `lower(…)`; при равенстве — `id` в ту же сторону. Кириллицу `lower` у SQLite не приводит — тест на PostgreSQL. Проект у задач страницы догружается одним запросом (`selectinload`).

## Статистика

`GET /api/tasks/statistics/users` (admin) проксирует `GET /api/time/statistics/users` time-service с токеном пользователя и отдаёт ответ как есть (поля — в [README time-service](../time-service/README.md)); сетевая ошибка или не-200 от time — 502 без деталей, причина в логе. Клиент — один `httpx.AsyncClient` на процесс (lifespan, `app/time_client.py`, `base_url` = `TIME_SERVICE_URL`), таймауты: соединение 2 с, ответ 7 с — time обрывает запрос к базе через 5 с (`statement_timeout`), gateway ждёт 30 с.

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

Проверка готовности: `GET http://127.0.0.1:8002/ready` — 200 `{"ready": true}`, если база доступна и схема не старше кода (ревизия в `alembic_version` равна head миграций или незнакома — новее); иначе 503 с причиной в `reason` (`schema not migrated`, `schema revision … is older than code …`, `database unavailable`). Эндпоинт вне `/api`, через gateway недоступен — его опрашивают healthcheck compose и readiness-проба Kubernetes. `GET /` — только «процесс отвечает» (liveness).

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны. Тесты миграций, `/ready`, таймаутов к базе и порядка списков на PostgreSQL идут, только если задана `TEST_POSTGRES_URL` — см. [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.
