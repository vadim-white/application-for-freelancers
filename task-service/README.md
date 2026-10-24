# Task Service (task-service)

Проекты и задачи; каждый пользователь видит только свои, администратор — все. Порт — 8002. OpenAPI: http://127.0.0.1:8002/docs

## Списки

`GET /api/tasks/projects` и `GET /api/tasks/tasks` отдают конверт `{items, total, limit, offset}` (`limit` 1–200, по умолчанию 50; `total` — с теми же фильтрами). Белые списки `sort` и фильтры — в [«API» корневого README](../README.md#api). Порядок одинаков на SQLite и PostgreSQL: `status` сортируется выражением `CASE` в порядке объявления `TaskStatus` (иначе SQLite сортирует по алфавиту), `NULL` — `NULLS LAST` в обе стороны, `updated_at` — `coalesce(updated_at, created_at)` (до первой правки `updated_at` пуст), `title` и `name` — по `lower(…)`; при равенстве — `id` в ту же сторону. Кириллицу `lower` у SQLite не приводит — тест на PostgreSQL. Проект у задач страницы догружается одним запросом (`selectinload`).

У каждого проекта списка есть `tasks_count` и `tasks_preview` — по активным задачам проекта (архивные не считаются): `COUNT(*) … GROUP BY project_id` и `ROW_NUMBER() OVER (PARTITION BY project_id ORDER BY created_at, id)` с `rn <= 3`, оба по `id` страницы, то есть два запроса на любое число проектов; пустая страница их не делает. Схема — `ProjectListItem`, а `ProjectRead` (одиночный проект и вложенный `project` у задачи) полей не получает. Задачи проекта принадлежат его владельцу, поэтому у admin счётчики чужих проектов верные, а у user чужих проектов в списке нет.

## Правка (`PATCH`)

`PATCH /api/tasks/projects/{id}` и `PATCH /api/tasks/tasks/{id}` — merge-patch: схемы `ProjectPatch` и `TaskPatch` (`extra="forbid"`: неизвестное поле, в том числе `owner_id`, — 422), `crud` пишет только поля из `model_fields_set`, поэтому нет поля — не трогать, явный `null` — очистить (`description`, `deadline`, `project_id` задачи — вынос из проекта, владелец прежний; `description` проекта). `null` у `title`, `status`, `is_active`, `name` модель пропускает, 422 даёт валидатор по `model_fields_set` (как `UserAdminUpdate` в auth). Значение, равное текущему, SQLAlchemy изменением не считает: `UPDATE` нет, `updated_at` прежний. Перенос задачи проверяется, только когда `project_id` прислан и не `null`: в чужой проект user — 404, admin в проект другого владельца — 400. Лог правки задачи пишет имена полей, не значения. `PUT` удалён — 405.

Название (`title`, `name`) в `…Create` и `…Patch` — тип `Title`: пробелы по краям обрезаются, затем 1–255 символов (колонка `VARCHAR(255)`: без ограничения PostgreSQL отвечал 500, SQLite пропускал). Ограничение только на вводе: ответы (`…Read` от `…Base`) отдают сохранённые названия как есть. `deadline` в `TaskCreate` и `TaskPatch` — `AwareDatetime`, без пояса — 422.

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

Запущенные сервисы не нужны. Тесты миграций, `/ready`, таймаутов к базе, порядка списков, длины названия и очистки полей на PostgreSQL идут, только если задана `TEST_POSTGRES_URL` — см. [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.
