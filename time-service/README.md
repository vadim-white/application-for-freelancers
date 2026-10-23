# Time Service (time-service)

Учёт времени по задачам: записи времени и статистика по пользователям. Порт — 8003. OpenAPI: http://127.0.0.1:8003/docs

## Таймер и записи

- `GET /api/time/timer`, `POST /api/time/timer/start`, `POST /api/time/timer/stop` — серверный таймер, у пользователя свой и один (описание ответов — [«API» в корневом README](../README.md#api)). Старт на другой задаче в одной транзакции закрывает идущую запись и открывает новую; старт той же задачи возвращает идущую. Один идущий таймер гарантирует частичный уникальный индекс `ux_time_entries_running`: при параллельном старте с другой реплики транзакция повторяется один раз («побеждает последний»), не удалось — 409.
- Старт проверяет задачу у task-service: `GET {TASK_SERVICE_URL}/api/tasks/tasks/{id}` с заголовком `Authorization` пользователя (task сам решает, чья задача: чужая — 404, admin видит любую, запись — на admin). Ответы старта: задачи нет или чужая — 404 «Task not found»; задача или её проект с `is_active=false` — 409 «Task is archived» (в том числе на ту же идущую задачу: проверка раньше идемпотентного ответа, идущую запись она не трогает); таймаут, сеть, 5xx — 503 «Task service unavailable»; 401/403 от task (тот же токен здесь уже принят — значит, рассинхрон настроек) — 502. Причина — только в логе (`app.task_client`). Клиент — один `httpx.AsyncClient` на процесс (lifespan), таймауты: соединение 2 с, ответ 3 с. Повтора нет: на перегруженном узле (одновременная перекатка всех Deployment) соединение может не уложиться в 2 с — 503, клиент повторяет сам ([«Известные ограничения»](../k8s/README.md#известные-ограничения)). Вызов — асинхронная зависимость до тела эндпоинта и до транзакции, сам эндпоинт синхронный: соединение с базой во время вызова не занято. Стоп и `GET /timer` в task не ходят и работают без него; идущий таймер на задаче, ушедшей в архив, не останавливается.
- Запись: `started_at`, `stopped_at` (пусто — таймер идёт), `duration_seconds` — целые секунды вниз, считает сервер при остановке. «Сейчас» — `crud.now()`, UTC.
- Время хранится в UTC. SQLite отдаёт его без пояса — тип `UTCDateTime` (`app/models.py`) пишет в UTC и возвращает время всегда с поясом UTC, на SQLite и PostgreSQL одинаково.
- Ручные записи и правка: `POST /api/time/time-entries` (`task_id`, `started_at`, `stopped_at`, `description`), `PATCH` и `DELETE /api/time/time-entries/{id}`. Проверка задачи — та же `fetch_usable_task`, вызывается асинхронной зависимостью до тела эндпоинта и до обращения к базе (как у старта таймера); у `PATCH` — только если `task_id` есть в теле. Время сверяет `crud.check_times` с допуском 1 минута на расхождение часов: начало и конец не позже «сейчас» + 1 минута, конец не раньше начала. `stopped_at` у идущей записи не ставится (422). При изменении времени закрытой записи сервер пересчитывает `duration_seconds`.
- Список `GET /api/time/time-entries` — конверт `{items, total, limit, offset}`, `limit` 1–200 (по умолчанию 50), фильтры `task_id`, `user_id` (admin), `from` включительно / `to` не включительно по `started_at`, сортировка `±started_at` и `id`. Запросы укладываются в `statement_timeout` 5 с; индекс `(user_id, started_at)`.
- Статистика `GET /api/time/statistics/users` (admin): `entries_count`, `tasks_count` (`count(distinct task_id)`), `total_seconds`, `avg_seconds_per_task` (`round(total_seconds / tasks_count)`) по закрытым записям (у идущих `duration_seconds` пусто). Email и имя фронтенд берёт сам.
- Схема `time_entries`: `id`, `task_id`, `user_id`, `description`, `started_at` (NOT NULL), `stopped_at`, `duration_seconds`, `created_at`, `updated_at`; `CHECK (stopped_at IS NULL OR stopped_at >= started_at)` и `CHECK (duration_seconds IS NULL OR duration_seconds >= 0)`, индекс идущего таймера `ux_time_entries_running` — `(user_id) WHERE stopped_at IS NULL`. Переход со старой схемы (`minutes`, `date`, `is_active`) — expand/contract в три выкатки: expand (`5ea47ccd8dc7`) добавил новые колонки, код писал обе схемы; contract (`1a3e7ba4c4e7`) дозаполнил записи, которые старые поды успели создать в окне expand, поставил `NOT NULL` и CHECK, вернул индексу условие «нет `stopped_at`» и дал `is_active` значение по умолчанию `true` (код до contract требует его в ответе); код contract старые колонки уже не читает и не пишет. Третья миграция (`30ac5e04a1c1`) удаляет `minutes`, `date`, `is_active` — отдельной выкаткой после кода, который их не знает: ORM перечисляет в `SELECT` все колонки модели, и под с моделью, где колонка ещё есть, на схеме без неё падает. `alembic check` сравнивает схему и модели целиком.
- На SQLite `DROP COLUMN` в batch пересоздаёт таблицу; CHECK и частичный индекс переносятся (проверяет тест миграций). Откат удаления возвращает три колонки nullable: `is_active` — со значением `true` у всех строк и по умолчанию, `date` — с `now()` по умолчанию, но пустым у существующих строк, `minutes` — пустым. Код contract их не читает; откат ниже expand (`minutes NOT NULL`) на базе с записями после contract не пройдёт.
- Миграции contract и удаления колонок на PostgreSQL ставят `SET LOCAL lock_timeout = '3s'`. `ALTER TABLE` ждёт `ACCESS EXCLUSIVE`, и все запросы к таблице встают в очередь за ним. Запросы приложения короче 5 с (`statement_timeout`), поэтому ждать дольше незачем: миграция падает, Job повторяет её, а старые поды продолжают работать.

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
