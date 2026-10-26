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

Список пользователей: `GET /api/auth/users` — только admin; роль берётся из базы (`crud.get_current_admin`), а не из токена, поэтому снятый admin получает 403 сразу. Ответ `{items, total, limit, offset}`, `limit` 1–200 (по умолчанию 50), `offset` ≥ 0, `sort` — `created_at`, `-created_at` (по умолчанию), `email`, `-email`, при равенстве по `id` (сортировки по `role` нет). Фильтры: `role`, `is_active`, `q` (подстрока в email или имени без учёта регистра, 1–100 символов, `%`, `_` и `\` — обычные символы), `id` (повторяемый, до 200). Поиск `q` по кириллице в другом регистре работает на PostgreSQL, на SQLite `lower()` не-ASCII не приводит. `created_at` отдают также `/me` и `register`.

Смена роли и отключение: `PATCH /api/auth/users/{id}` — только admin (по базе), тело `{role?, is_active?}` (`UserAdminUpdate`: нет поля — не трогать, `null` и неизвестные поля — 422, пустое тело — 200 без изменений). Себя — 409, нет пользователя — 404. `crud.update_user_by_admin` в одной транзакции блокирует строки активных admin (`lock_active_admin_ids`: `SELECT … FOR UPDATE ORDER BY id`) и проверяет, что тот, кто делает запрос, среди них (иначе 403). Раз менять себя нельзя, после правки он остаётся активным admin — admin в базе не может закончиться, даже если двое понижают друг друга одновременно: второй дождётся блокировки, увидит, что сам уже не admin, и получит 403 (тест на PostgreSQL; на SQLite `FOR UPDATE` нет, запись там и так одна за раз). Удаления нет (`DELETE` — 405). Каждое реально изменённое поле — строка в `user_audit` (`actor_id`, `target_id`, `field`, `old_value`, `new_value` строками — `user`/`admin`, `true`/`false`, `created_at`) в той же транзакции; API нет, читать через psql, например `SELECT * FROM user_audit WHERE target_id = 5 ORDER BY id`. Миграция `6f0e3b36cb48` только добавляет таблицу.

Счётчик неудачных входов: `login` сначала засчитывает попытку по email (`crud.count_login_attempt`) и только потом проверяет пароль. Счёт — одна строка `login_attempts` (`email`, `attempts`, `window_start`) на адрес, без FK на `users`: незарегистрированный email считается так же. Запись — один `INSERT … ON CONFLICT (email) DO UPDATE … RETURNING` (диалект `postgresql` или `sqlite`): окно истекло — `attempts = 1` и новое `window_start`, иначе `attempts + 1`; коммит сразу. Поэтому параллельные попытки через разные реплики получают разные номера, и за окно bcrypt проверяет не больше `LOGIN_MAX_ATTEMPTS` паролей на адрес. Номер больше `LOGIN_MAX_ATTEMPTS` (5) — 429 «Too many login attempts», `Retry-After` — секунды до `window_start + LOGIN_WINDOW_SECONDS` (900), не меньше 1; пароль не проверяется, окно не сдвигается. Верный пароль (`crud.clear_login_attempts`) удаляет строку адреса и все строки с истёкшим окном (по индексу `window_start`), затем проверяется `is_active` (403). `refresh` и `register` не считаются. Время — `crud.now()` (подменяется в тестах), колонка — `UTCDateTime` (SQLite отдаёт время без пояса). Миграция `e8b2cc9410c9` только добавляет таблицу: старые поды в окне выкатки её не знают, попытки через них не считаются.

Проверка готовности: `GET http://127.0.0.1:8001/ready` — 200 `{"ready": true}`, если база доступна и схема не старше кода (ревизия в `alembic_version` равна head миграций или незнакома — новее); иначе 503 с причиной в `reason` (`schema not migrated`, `schema revision … is older than code …`, `database unavailable`). Эндпоинт вне `/api`, через gateway недоступен — его опрашивают healthcheck compose и readiness-проба Kubernetes. `GET /` — только «процесс отвечает» (liveness).

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны. Тесты миграций, `/ready`, таймаутов к базе, гонки двух admin при смене роли и счётчика входов (8 параллельных неверных входов — ровно 5 × 401 и 3 × 429) на PostgreSQL идут, только если задана `TEST_POSTGRES_URL` — см. [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`. `LOGIN_MAX_ATTEMPTS` (5) и `LOGIN_WINDOW_SECONDS` (900) — счётчик неудачных входов; в compose и k8s не задаются, действуют значения по умолчанию.
