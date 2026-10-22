# Time Service (time-service)

Учёт времени по задачам: записи времени и статистика по пользователям. Порт — 8003. OpenAPI: http://127.0.0.1:8003/docs

## Таймер и записи

- `GET /api/time/timer`, `POST /api/time/timer/start`, `POST /api/time/timer/stop` — серверный таймер, у пользователя свой и один (описание ответов — [«API» в корневом README](../README.md#api)). Старт на другой задаче в одной транзакции закрывает идущую запись и открывает новую; старт той же задачи возвращает идущую. Один идущий таймер гарантирует частичный уникальный индекс `ux_time_entries_running`: при параллельном старте с другой реплики транзакция повторяется один раз («побеждает последний»), не удалось — 409.
- Старт проверяет задачу у task-service: `GET {TASK_SERVICE_URL}/api/tasks/tasks/{id}` с заголовком `Authorization` пользователя (task сам решает, чья задача: чужая — 404, admin видит любую, запись — на admin). Ответы старта: задачи нет или чужая — 404 «Task not found»; задача или её проект с `is_active=false` — 409 «Task is archived» (в том числе на ту же идущую задачу: проверка раньше идемпотентного ответа, идущую запись она не трогает); таймаут, сеть, 5xx — 503 «Task service unavailable»; 401/403 от task (тот же токен здесь уже принят — значит, рассинхрон настроек) — 502. Причина — только в логе (`app.task_client`). Клиент — один `httpx.AsyncClient` на процесс (lifespan), таймауты: соединение 2 с, ответ 3 с. Вызов — асинхронная зависимость до тела эндпоинта и до транзакции, сам эндпоинт синхронный: соединение с базой во время вызова не занято. Стоп и `GET /timer` в task не ходят и работают без него; идущий таймер на задаче, ушедшей в архив, не останавливается. Старый `POST /time-entries {task_id, minutes}` задачу не проверяет (уходит вместе со старым телом).
- Запись: `started_at`, `stopped_at` (пусто — таймер идёт), `duration_seconds` — целые секунды вниз, считает сервер при остановке. «Сейчас» — `crud.now()`, UTC.
- Время хранится в UTC. SQLite отдаёт его без пояса — тип `UTCDateTime` (`app/models.py`) пишет в UTC и возвращает время всегда с поясом UTC, на SQLite и PostgreSQL одинаково.
- Ручные записи и правка: `POST /api/time/time-entries` (`task_id`, `started_at`, `stopped_at`, `description`), `PATCH` и `DELETE /api/time/time-entries/{id}`. Проверка задачи — та же `fetch_usable_task`, вызывается асинхронной зависимостью до тела эндпоинта и до обращения к базе (как у старта таймера); у `PATCH` — только если `task_id` есть в теле. Время сверяет `crud.check_times` с допуском 1 минута на расхождение часов: начало и конец не позже «сейчас» + 1 минута, конец не раньше начала. `stopped_at` у идущей записи не ставится (422), правка времени записи старого пода без `started_at` — 409 (она дозаполняется миграцией contract). При изменении времени закрытой записи сервер пересчитывает `duration_seconds` и `minutes`.
- Список `GET /api/time/time-entries` — конверт `{items, total, limit, offset}`, `limit` 1–200 (по умолчанию 50), фильтры `task_id`, `user_id` (admin), `from` включительно / `to` не включительно по `started_at`, сортировка `±started_at` и `id`. Записи старых подов (без `started_at`) идут в конце при любой сортировке (`NULLS LAST`) и под `from`/`to` не попадают. Запросы укладываются в `statement_timeout` 5 с; индекс `(user_id, started_at)`.
- Статистика `GET /api/time/statistics/users` (admin): `entries_count`, `tasks_count` (`count(distinct task_id)`), `total_seconds`, `avg_seconds_per_task` (`round(total_seconds / tasks_count)`) по закрытым записям; идущие и записи старых подов (`duration_seconds` пусто) не считаются — они появятся в статистике после дозаполнения в contract. Email и имя фронтенд берёт сам.
- Схема в состоянии expand: рядом с новыми колонками остаются `minutes` (у закрытой записи — длительность вверх до минуты, у идущей — 1; пишется и у ручной записи, и при правке времени), `date`, `is_active`; их читают старые поды во время перекатки. Записи, которые старый код успел создать после миграции, остаются без `started_at` — идущим таймером не считаются (условие индекса `started_at IS NOT NULL AND stopped_at IS NULL`). Старые колонки и запись `minutes` удаляются миграцией contract.

## Локальный запуск

1. Скопируйте `.env.example` в `.env`. `SECRET_KEY` должен совпадать во всех бэкенд-сервисах.
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
   uv run uvicorn app.main:app --reload --port 8003
   ```

Проверка готовности: `GET http://127.0.0.1:8003/ready` — 200 `{"ready": true}`, если база доступна и схема не старше кода (ревизия в `alembic_version` равна head миграций или незнакома — новее); иначе 503 с причиной в `reason` (`schema not migrated`, `schema revision … is older than code …`, `database unavailable`). Эндпоинт вне `/api`, через gateway недоступен — его опрашивают healthcheck compose и readiness-проба Kubernetes. `GET /` — только «процесс отвечает» (liveness).

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны. task-service в тестах — мок (`httpx.MockTransport`, фикстура `task_service` в `tests/conftest.py`: по умолчанию любая задача есть и активна). Тесты миграций, `/ready`, таймаутов к базе и гонки двух стартов таймера на PostgreSQL идут, только если задана `TEST_POSTGRES_URL` — см. [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.

`TASK_SERVICE_URL` — адрес task-service для проверки задачи (по умолчанию `http://127.0.0.1:8002`; compose — `http://ser-task:8002`, Kubernetes — ключ `task-url` ConfigMap). В compose time не ждёт task (`depends_on` нет: task ждёт time ради статистики, обратная зависимость — цикл); пока task не поднялся, старт отвечает 503.
