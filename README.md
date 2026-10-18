# Freelance Time Tracker

[![CI](https://github.com/vadim-white/application-for-freelancers/actions/workflows/ci.yml/badge.svg)](https://github.com/vadim-white/application-for-freelancers/actions/workflows/ci.yml)

Трекер задач и рабочего времени на микросервисной архитектуре. Бэкенд написан на FastAPI, фронтенд на Vue 3. Проект задуман как полноценная open-source альтернатива готовым решениям на Django: с раздельными сервисами, единой точкой входа и деплоем в контейнерах и Kubernetes.

Проект находится в активной разработке. Раздел [Текущее состояние](#текущее-состояние) описывает, что уже работает, а что ещё нет.

## Возможности

- Регистрация и вход по email и паролю, JWT (access и refresh токены), роли `user` и `admin`
- Проекты и задачи: создание, просмотр, редактирование, удаление, смена статуса. Пользователь работает только со своими проектами и задачами, администратор — со всеми
- Таймер на задачу: старт, пауза, остановка, запись затраченного времени
- Статистика по пользователям для администратора: выполненные задачи и затраченное время
- Профиль пользователя

## Архитектура

```
              Браузер → Frontend (nginx, :5173)
                  статика Vue 3 |  /api/* (прокси)
                               v
                       API Gateway (:8000)
                      /        |         \
                     v         v          v
             Auth Service  Task Service  Time Service
                (:8001)      (:8002)       (:8003)
                  |            |             |
               auth_db      task_db       time_db
```

| Компонент | Порт | Назначение |
|-----------|------|------------|
| gateway-service | 8000 | Единая точка входа, проксирование запросов на `/api/auth`, `/api/tasks`, `/api/time` |
| auth-service | 8001 | Пользователи, регистрация, вход, выдача и обновление токенов |
| task-service | 8002 | Проекты, задачи, статусы, агрегированная статистика |
| time-service | 8003 | Записи о затраченном времени, статистика по времени |
| frontend | 5173 (в контейнере 8080) | SPA на Vue 3, TypeScript, Pinia, Naive UI. В Docker — собранная статика за nginx, который проксирует `/api/` на gateway: браузер работает с одним адресом, CORS для фронтенда не нужен |

У каждого сервиса своя база данных, сервисы не ходят в чужие таблицы. Task Service обращается к Time Service по HTTP, когда собирает статистику.

В Kubernetes вход в кластер один — Gateway API (контроллер Envoy Gateway) на `http://127.0.0.1:8080`: `/api` уходит в API Gateway, всё остальное — во фронтенд. Сервисы приложения наружу не публикуются (все `ClusterIP`):

```
   Браузер → 127.0.0.1:8080 → Envoy (Gateway "entry", HTTPRoute "entry-routes")
                                 /api/*  → ser-gateway:8000 → auth, task, time
                                 /*      → ser-frontend:8080 (статика; его /api/ тоже проксируется на gateway)
```

## Стек

- Python 3.14, FastAPI, SQLAlchemy 2.0, Pydantic 2, драйвер PostgreSQL psycopg 3
- uv — зависимости Python (`pyproject.toml` + `uv.lock` в каждом сервисе), pytest
- PostgreSQL 15 (в Docker), SQLite для локальной разработки без контейнеров
- JWT (python-jose), хеширование паролей через bcrypt
- Vue 3, TypeScript, Pinia, Vue Router, Axios, Vite, Naive UI; Node.js 24 (сборка фронтенда), проверка типов — vue-tsc
- nginx (раздача собранного фронтенда и прокси `/api`)
- Docker, Docker Compose, Kubernetes

## Быстрый старт

### Через Docker Compose

Нужны Docker и Docker Compose.

```bash
git clone https://github.com/vadim-white/application-for-freelancers.git
cd application-for-freelancers
./scripts/init-env.sh        # создаёт .env со случайными SECRET_KEY и паролями баз (повторный запуск ничего не ломает)
docker compose up --build --wait
```

`--wait` возвращает управление, когда одноразовые контейнеры (миграции, seed) завершились с кодом 0, а auth, task, time, gateway, frontend и базы стали `healthy` (у сервисов проверка — публичный `GET /`, у баз — `pg_isready`). Поэтому сразу после команды можно входить под тестовыми пользователями. Без `--wait` стек тоже поднимется, но сервисы ещё какое-то время будут стартовать. Нужен Docker Compose v2 (проверено на 2.40.2).

Без `.env` `docker compose` не стартует и пишет «задайте в .env (./scripts/init-env.sh)». Скрипт создаёт корневой `.env` из `.env.example`; если `.env` уже есть, дописывает только отсутствующие ключи, существующие значения не трогает. Значения секретов он не печатает.

После запуска:

- приложение: http://localhost:5173 (nginx отдаёт собранный фронтенд и проксирует `/api/` на gateway)
- gateway: http://localhost:8000 (опубликован для curl, Swagger и smoke-прогона; фронтенд ходит к нему через nginx)
- документация сервисов (Swagger) доступна на `/docs` у каждого сервиса. В compose наружу опубликованы только gateway и frontend, поэтому Swagger остальных сервисов открывается при локальном запуске

Порты 5173 и 8000 по умолчанию открыты только на `127.0.0.1`: с других устройств в сети приложение недоступно. Чтобы открыть его, например, с телефона, задайте в `.env` `BIND_ADDR=0.0.0.0` (или разово `BIND_ADDR=0.0.0.0 docker compose up -d --wait`) и откройте `http://<IP-машины>:5173`. Фронтенд ходит к API через свой `/api`, поэтому `CORS_ORIGINS` для этого менять не нужно. Auth, task, time и базы наружу не публикуются при любом значении.

Таблицы auth-service, task-service и time-service создают одноразовые контейнеры `ser-auth-migrate`, `ser-task-migrate` и `ser-time-migrate` (`alembic upgrade head`), сервис стартует только после успешного завершения своей миграции. Если тома остались от версии без миграций, один раз выполните `docker compose down -v`: иначе миграция упадёт на уже существующих таблицах. То же после перехода на пароли из `.env`: пароль БД применяется только при создании тома.

Тестовых пользователей создаёт одноразовый контейнер `ser-auth-seed` (`python -m app.init_users`) после миграции auth, ser-auth стартует после него. Сам сервис при старте пользователей не создаёт. По умолчанию (`SEED_TEST_USERS=true` в `.env`, дефолт в `docker-compose.yml` тоже `true`): создаются пользователи, которых ещё нет, повторный запуск дублей не делает. Без тестовых пользователей: `SEED_TEST_USERS=false docker compose up --build` (seed пишет в лог «пропущено» и завершается с кодом 0, войти можно после регистрации). Вне Docker то же делает `uv run python -m app.init_users` в папке auth-service после `uv run alembic upgrade head`, если в `.env` указано `SEED_TEST_USERS=true`.

| Email | Пароль | Роль |
|-------|--------|------|
| admin@example.com | password123 | admin |
| user1@example.com | password123 | user |
| user2@example.com | password123 | user |

Остановить и удалить контейнеры вместе с данными:

```bash
docker compose down -v
```

### Локальный запуск без Docker

Нужны [uv](https://docs.astral.sh/uv/) (проверено на 0.13.1) и Node.js 24 (версия в `frontend/login_page/.nvmrc`). Python 3.14 (версия в `.python-version`) uv при необходимости скачает сам. Каждый сервис запускается в отдельном терминале со своим виртуальным окружением: `uv sync` создаёт `.venv` в папке сервиса и ставит в него зависимости строго по `uv.lock` (вместе с dev-группой для тестов), `uv run <команда>` выполняет команду в этом окружении, активировать его не нужно. Окружение `.venv`, созданное раньше через `python -m venv` с другой версией Python, uv пересоздаст сам. Добавить или обновить зависимость — `uv add 'пакет==версия'` в папке сервиса (меняет `pyproject.toml` и `uv.lock`, оба файла коммитятся вместе). В auth-service, task-service и time-service таблицы создаёт `uv run alembic upgrade head` (выполнить перед первым запуском и после обновления кода). Если `auth.db`, `task.db` или `time_service.db` осталась от версии без миграций, удалите её: на таблицах, созданных без Alembic, `alembic upgrade head` падает с ошибкой вида `table users already exists`. Базу выбирает обязательная переменная `DATABASE_URL`: для локального запуска в `.env.example` указан SQLite-файл в папке сервиса.

Перед первым запуском скопируйте в каждой папке сервиса и в `frontend/login_page` файл `.env.example` в `.env`. В `.env` всех четырёх бэкенд-сервисов впишите один и тот же `SECRET_KEY`. `DATABASE_URL` в auth, task и time уже есть в примере (SQLite). Без `SECRET_KEY` и `DATABASE_URL` сервисы не стартуют: значений по умолчанию нет, сервис сразу падает с ошибкой валидации настроек. Сгенерировать ключ: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Остальные значения из примеров подходят для локального запуска.

```bash
# auth-service
cd auth-service
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8001

# task-service
cd task-service
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8002

# time-service
cd time-service
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8003

# gateway-service
cd gateway-service
uv sync
uv run uvicorn app.main:app --reload --port 8000

# frontend
cd frontend/login_page
npm install
npm run dev
```

Типы фронтенда (TypeScript в `.ts` и `.vue`) проверяет `npm run typecheck` (`vue-tsc --noEmit`, код возврата ≠ 0 при ошибке); `npm run build` (`vite build`) типы не проверяет. Без локального Node — в Docker из корня репозитория: `docker run --rm -v "$PWD/frontend/login_page":/src:ro node:24-alpine sh -c 'cp -r /src /w && cd /w && rm -rf node_modules dist && npm ci && npm run typecheck'`.

Фронтенд обращается к API по относительному пути `/api`: `npm run dev` проксирует его на gateway `http://localhost:8000` (`server.proxy` в `vite.config.ts`), браузер остаётся на одном адресе, CORS не участвует. Переменная `VITE_API_BASE` в `frontend/login_page/.env` необязательна: задавайте её, только если фронтенд должен ходить на gateway напрямую, и тогда добавьте адрес фронтенда в `CORS_ORIGINS` gateway. Если в вашем `.env` осталась старая строка `VITE_API_BASE=http://localhost:8000`, уберите её, чтобы запросы шли через прокси.

### Тесты

Тесты есть у gateway, auth-service, task-service и time-service. Им не нужны запущенные сервисы: внешние HTTP-вызовы (gateway → сервисы, task → time) подменяются в тестах, базы — временная SQLite (тест миграций дополнительно идёт на PostgreSQL, см. ниже). Запуск в папке сервиса (`<service>` — `gateway-service`, `auth-service`, `task-service` или `time-service`):

```bash
cd <service>
uv run pytest -q
```

uv сам поставит Python 3.14 и зависимости из `uv.lock` вместе с dev-группой (`pytest`, `httpx2` — клиент для `TestClient` Starlette, `pytest-cov`). Покрытие: `uv run pytest --cov=app`.

#### Тест миграций на PostgreSQL

Тест миграций (`tests/test_migrations.py` в auth, task и time: `upgrade head` → `alembic check` → `downgrade base` → `upgrade head`) идёт на двух базах: SQLite (всегда) и PostgreSQL 15 (если задана `TEST_POSTGRES_URL`). Без переменной тесты PostgreSQL помечаются `skipped` с причиной. На PostgreSQL проверяется то, чего не видно на SQLite: после `downgrade base` не остаётся ни таблиц, ни типов enum (`downgrade` вручную удаляет enum, PostgreSQL сам этого не делает), а в task внешний ключ `tasks.project_id` действует: задача с несуществующим проектом даёт `IntegrityError`.

Каждый тест работает в собственной схеме (`CREATE SCHEMA mig_…` / `DROP SCHEMA … CASCADE` после теста), поэтому база может быть общей для трёх сервисов; важно только, чтобы это была тестовая база, а не база стека. Локально:

```bash
docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=test postgres:15-alpine
cd task-service                          # или auth-service, time-service
TEST_POSTGRES_URL=postgresql+psycopg://postgres:test@127.0.0.1:55432/postgres uv run pytest -q -rs
docker stop pg-test
```

Тесты в контейнере (рецепт Docker выше) подключаются к PostgreSQL по имени в общей сети: `docker network create t15`, `docker run -d --rm --network t15 --name pg -e POSTGRES_PASSWORD=test postgres:15-alpine`, затем в команду тестов добавить `--network t15 -e TEST_POSTGRES_URL=postgresql+psycopg://postgres:test@pg:5432/postgres`. После проверки: `docker stop pg && docker network rm t15`.

#### Покрытие

`uv run pytest --cov=app --cov-report=term-missing` печатает покрытие и непокрытые строки. Порог — `[tool.coverage.report] fail_under` в `pyproject.toml` сервиса (gateway 98 %, auth 91 %, task 95 %, time 97 %, чуть ниже фактического 100 / 93 / 97 / 99 %); он срабатывает только при запуске с `--cov`. В `addopts` `--cov` не добавлен: обычный `uv run pytest` и прогон одного файла от порога не зависят. Порог защищает от падения покрытия, гнаться за 100 % не нужно.

Без uv на машине — в Docker, в официальном образе uv с Python 3.14 на том же Debian, что и `python:3.14-slim` у сервисов:

```bash
docker run --rm -v "$PWD/<service>":/src:ro ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim sh -c \
  "cp -r /src /app && cd /app && rm -rf .env .venv && uv run --locked pytest -q"
```

#### Сквозной прогон

[tests/smoke.sh](tests/smoke.sh) — curl-прогон через gateway: авторизация, доступ «только свои», записи времени, `/health`, CORS. Идемпотентен, проходит на чистой базе и повторно. Готовности стека не ждёт.

```bash
docker compose up --build -d --wait
bash tests/smoke.sh                      # режим compose: 116 проверок

./scripts/k8s-deploy.sh                  # кластер kind (см. k8s/README.md)
SMOKE_MODE=k8s bash tests/smoke.sh       # режим k8s: 114 проверок через http://127.0.0.1:8080
```

`/health` gateway всегда отвечает 200, а доступность сервисов пишет в теле (`upstreams`), поэтому smoke проверяет тело: `auth`, `task`, `time` — все `true`. В k8s запрос идёт изнутри пода `ser-gateway` (через вход `/health` отдаёт фронт). Код выхода 0 — все проверки пройдены.

#### e2e в браузере (Playwright)

[tests/e2e/](tests/e2e/) — тесты фронтенда в headless Chromium (pytest-playwright), вход через форму, как у пользователя:

- **авто-refresh**: на `/dashboard` `access_token` заменяется на `abc` и страница перезагружается. Дашборд шлёт параллельные запросы (два `GET /api/auth/me`), оба получают 401, ожидается ровно один `POST /api/auth/refresh` (200). Затем каждый упавший запрос повторяется с 200, страница остаётся на `/dashboard`;
- **неудачный refresh**: подменены оба токена, ожидается один refresh с 401. Токены удаляются из `localStorage`, открывается `/login`;
- **«только свои»**: user1 создаёт проект через UI (имя с меткой прогона). user2 не видит его ни в `GET /api/tasks/projects`, ни на странице, а по id получает 404. admin видит проект.

В каждом тесте проверяется, что все запросы страницы идут на тот же origin, что и фронт. Тесты создают только свои объекты (метка `e2e-<время>-<случайное>`), seed-пользователи те же, что у smoke. Стек должен быть уже поднят: скрипт его не запускает.

```bash
docker compose up --build -d --wait
bash tests/e2e/run.sh                                       # compose: http://127.0.0.1:5173 (по умолчанию)
E2E_BASE_URL=http://127.0.0.1:8080 bash tests/e2e/run.sh    # кластер kind, через вход
bash tests/e2e/run.sh -k refresh -v                         # аргументы передаются pytest
```

`run.sh` собирает образ `freelance-e2e` из [tests/e2e/Dockerfile](tests/e2e/Dockerfile) и запускает в нём pytest. База — `mcr.microsoft.com/playwright/python:v1.63.0-noble` (браузеры, Python 3.12). Python-зависимости ставятся `uv sync --locked` строго по `tests/e2e/uv.lock`, uv берётся бинарником из `ghcr.io/astral-sh/uv:0.13.1`. Оба образа закреплены по digest. Версия пакета `playwright` (1.63.0) равна версии образа. Сеть:
- **macOS** (Docker Desktop): host-сети нет, порты стека опубликованы на `127.0.0.1` хоста. Внутри контейнера поднимается TCP-форвардер `127.0.0.1:<порт>` → `host.docker.internal:<порт>` ([forward.py](tests/e2e/forward.py)), и браузер открывает тот же адрес, что и на хосте;
- **Linux**: `docker run --network host`, форвардер не нужен.

Порт берётся из `E2E_BASE_URL`. Скриншот и trace упавшего теста сохраняются в `tests/e2e/test-results/` (каталог в `.gitignore`), trace открывается командой `uv run playwright show-trace <trace.zip>` (в `tests/e2e`) или на trace.playwright.dev. С uv на машине тесты можно запустить и без Docker: `cd tests/e2e && uv run playwright install chromium && uv run pytest`.

### Линтер

Python-код четырёх сервисов (`app/`, `tests/`, `migrations/`) проверяет и форматирует [ruff](https://docs.astral.sh/ruff/) 0.17.1, настройки — [ruff.toml](ruff.toml) в корне: правила `E`, `F`, `W`, `I`, `B`, `UP`, длина строки 100. Версия одна для всех и задаётся в команде, в dev-группы сервисов ruff не добавлен. Запуск из корня репозитория:

```bash
uvx ruff@0.17.1 check .              # замечания линтера, код 0 — чисто
uvx ruff@0.17.1 format --check .     # код 0 — форматирование не нужно
uvx ruff@0.17.1 check --fix .        # исправить то, что ruff умеет сам
uvx ruff@0.17.1 format .             # отформатировать
```

Без uv на машине — тот же образ, что для тестов: `docker run --rm -v "$PWD":/repo -w /repo ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim uvx ruff@0.17.1 check --no-cache .` (`--no-cache` — чтобы не появлялся `.ruff_cache`).

Отключены `B008` (`Depends()` / `Query()` в значениях по умолчанию — обычный приём FastAPI) и `UP042` (`class X(str, Enum)` → `StrEnum` меняет `str()` у значений). В `tests/conftest.py` импорты приложения стоят после `os.environ[...] = …`: config и engine читают окружение при импорте. Порядок этих строк менять нельзя, а `E402` такие присваивания нарушением не считает. `init_db.py` в проверку не входит. У `tests/e2e/` свой `[tool.ruff]` в `pyproject.toml`: правила из корневого `ruff.toml`, но `target-version = "py312"`. e2e работает на Python 3.12 из образа Playwright, а с py314 `ruff format` переписывает `except (A, B):` в синтаксис 3.14 без скобок.

Массовое переформатирование сделано отдельным коммитом, его хеш записан в [.git-blame-ignore-revs](.git-blame-ignore-revs). GitHub пропускает такие коммиты в blame сам, локально нужно один раз выполнить в своей копии репозитория:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Если файла нет (например, в старой ветке до шага 1.5.7), `git blame` с этой настройкой падает с ошибкой `could not open object name list`.

Shell-скрипты в `scripts/` проверяет [shellcheck](https://www.shellcheck.net/) v0.11.0 (в CI, замечаний 0): `docker run --rm -v "$PWD":/mnt:ro -w /mnt koalaman/shellcheck:v0.11.0 scripts/*.sh`. `tests/smoke.sh` пока не проверяется: там много замечаний о кавычках, их исправление запланировано вместе с укреплением smoke.

### Миграции

Схему БД auth-service, task-service и time-service ведёт Alembic (`<service>/migrations/`). Применяются они отдельно от приложения: `alembic upgrade head` (в compose — сервисы `ser-*-migrate`, в Kubernetes — Job `*-migrate`). Новая миграция создаётся автогенерацией по изменённым моделям (`<service>` — `auth`, `task` или `time`, нужен запущенный стек, у которого база уже на последней ревизии):

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD/<service>-service/migrations:/app/migrations" \
  ser-<service>-migrate alembic revision --autogenerate -m "что изменилось"
```

Каталог `migrations` монтируется с хоста, иначе файл ревизии останется внутри одноразового контейнера. `--user` нужен, потому что в образе процесс работает как `app` (UID 10001): с ним файл создаётся от вашего пользователя, и рецепт работает на Linux (на Docker Desktop для macOS права транслируются и без него). Сервис собирается из образа, поэтому сначала пересоберите его (`docker compose build ser-<service>`), чтобы в образе были изменённые модели.

Сгенерированный файл (`migrations/versions/<дата>-<ревизия>_….py`) нужно вычитать вручную:
- `server_default=sa.text('now()')` заменить на `sa.func.now()`: на SQLite функции `now()` нет, тест миграций упадёт;
- для enum в `downgrade` после `op.drop_table` добавить `sa.Enum(name='…').drop(op.get_bind(), checkfirst=True)`: PostgreSQL не удаляет тип вместе с таблицей;
- убрать комментарии «auto generated».

Затем проверьте цикл `alembic upgrade head` → `alembic check` → `alembic downgrade base` → `alembic upgrade head`. Его выполняет `tests/test_migrations.py`: при расхождении моделей и миграций тест падает. Применить новую ревизию к базе стека: `docker compose up --build -d` (migrate-сервис выполнится сам) или `docker compose run --rm --no-deps ser-<service>-migrate alembic upgrade head`. Вне Docker те же команды запускаются в папке сервиса через uv: `uv run alembic upgrade head`, `uv run alembic check` и т. д.

### Kubernetes

Приложение запускается в локальном кластере [kind](https://kind.sigs.k8s.io/) (Kubernetes в Docker, один узел). Подробная инструкция — **[k8s/README.md](k8s/README.md)**: требования и версии, что делает каждый скрипт, устройство манифестов, диагностика (логи, Job, события), удаление кластера и известные ограничения. Нужны Docker (4 ГБ памяти), kind и kubectl.

```bash
brew install kind                # проверено на v0.33.0
./scripts/kind-up.sh             # кластер freelance + Envoy Gateway + сборка и загрузка образов ser-*:latest
./scripts/init-k8s-env.sh        # k8s/overlays/local/app.env и db.env со случайными секретами
./scripts/k8s-deploy.sh          # манифесты, миграции, тестовые пользователи, ожидание готовности
open http://127.0.0.1:8080       # приложение (вход admin@example.com / password123)
```

Кратко:
- манифесты собирает kustomize: [k8s/base](k8s/base) без локальных допущений, [k8s/overlays/local](k8s/overlays/local) для kind (Secret'ы из `app.env` и `db.env`, `imagePullPolicy: Never`, класс входа), [k8s/overlays/local-seed](k8s/overlays/local-seed) добавляет Job тестовых пользователей;
- вход один — Gateway API (Envoy Gateway v1.9.2) на `http://127.0.0.1:8080`: `/api` → `ser-gateway`, остальное → `ser-frontend`, все сервисы `ClusterIP`;
- миграции — Job `auth-migrate`, `task-migrate`, `time-migrate`, seed — Job `auth-seed`. Порядок задаёт `k8s-deploy.sh`. Деплоить только через него: Job неизменяемы, голый `kubectl apply -k` поверх старых Job падает или не перезапускает миграции;
- по две реплики у auth, task, time, gateway и frontend, базы — по одной;
- Pod Security Admission `restricted` (не root, без привилегий, корень только на чтение), NetworkPolicy по умолчанию запрещают всё, кроме нужных связей;
- сквозной прогон против кластера — `SMOKE_MODE=k8s bash tests/smoke.sh` (114 проверок).

Удалить кластер: `kind delete cluster --name freelance`.

### CI

GitHub Actions, workflow [.github/workflows/ci.yml](.github/workflows/ci.yml). Запускается на каждый push в любую ветку, на pull request и вручную (Actions → CI → Run workflow). Новый push в ту же ветку отменяет устаревший прогон (`concurrency`). У каждого job есть `timeout-minutes`, права токена — только `contents: read`. Jobs идут параллельно:

| Job | Что проверяет |
|---|---|
| `lint` | `ruff check` и `ruff format --check` (0.17.1), shellcheck `scripts/*.sh`, [actionlint](https://github.com/rhysd/actionlint) по workflow (и shellcheck внутри `run:`), [gitleaks](https://github.com/gitleaks/gitleaks) по всей истории git (найденное печатается скрытым, `--redact`) |
| `python` (×4: auth, task, time, gateway) | `uv sync --locked`, `uv run pytest --cov=app`: порог покрытия из `pyproject.toml`, тест миграций на PostgreSQL 15 (service container, `TEST_POSTGRES_URL`). Пропущенный тест роняет job: значит, база не подключилась |
| `frontend` | Node из `.nvmrc` (24), `npm ci`, `npm run typecheck`, `npm run build` |
| `static` | `docker compose config --quiet` на `.env` от `init-env.sh`, kubeconform v0.8.0 по выводу `kubectl kustomize` обоих overlay (как в [k8s/README.md](k8s/README.md#диагностика)) |
| `compose` | с чистого раннера: `init-env.sh` → `docker compose up --build -d --wait` → smoke (116) → e2e (`http://127.0.0.1:5173`), в конце `down -v` |
| `kind` | `kind-up.sh` → `init-k8s-env.sh` → `k8s-deploy.sh` → smoke k8s (114) → e2e через вход (`http://127.0.0.1:8080`) → `kubectl apply --dry-run=server` обоих overlay |

Где смотреть: вкладка **Actions** репозитория, workflow **CI**, бейдж в начале README показывает статус последнего прогона. Если падают compose или kind, отдельный шаг «диагностика» печатает состояние: для compose — `docker compose ps -a` и последние строки логов, для kind — поды и Job, события, `describe gateway entry`, логи подов (и прошлых контейнеров) и контроллера Envoy Gateway. Скриншоты и trace упавших e2e-тестов приходят артефактом прогона (`e2e-compose`, `e2e-kind`, хранятся 7 дней). Повторить job локально можно теми же командами, что в разделах «Тесты», «Линтер» и в [k8s/README.md](k8s/README.md).

Прогон целиком занимает около 4,5 минуты: дольше всех идёт `kind` (~4 мин: `kind-up.sh` ~1,5 мин, деплой ~1 мин, smoke и e2e ~1,5 мин), `compose` ~2 мин, остальные jobs укладываются в 10–40 с. Лимит `timeout-minutes` — 5 минут у лёгких jobs, 10 у `compose`, 15 у `kind`.

Секреты в CI не хранятся: `init-env.sh` и `init-k8s-env.sh` генерируют их заново в каждом прогоне. Сразу после этого workflow регистрирует значения (для k8s — и их base64) через `::add-mask::`, и если значение где-то всплывёт, GitHub заменит его в логе на `***`. Маскирование — только страховка: `docker compose config` запускается только с `--quiet` (без него печатает пароли), вывод `kubectl kustomize` (Secret'ы в base64) идёт только в pipe, `set -x` в workflow и скриптах не включать.

Версии закреплены так же, как локально:
- actions — полным SHA коммита с версией в комментарии (`actions/checkout@3d3c42e… # v7.0.1`): тег можно перевесить на другой код, SHA — нет. При обновлении берётся SHA из тега релиза, комментарий меняется вместе с ним. actionlint не проверяет входы actions, закреплённых по SHA, поэтому входы сверяются с `action.yml` этой версии вручную;
- инструменты — образы по digest (shellcheck, actionlint, gitleaks, kubeconform) и бинарники с проверкой sha256: uv 0.13.1 (`checksum` у setup-uv), kubectl v1.35.9 (на раннере kubectl 1.37, а сервер kind — 1.35, это больше допустимой разницы в одну минорную версию). У kind проверяется версия на раннере (v0.33.0): если образ раннера её поменяет, job упадёт с понятной ошибкой;
- PostgreSQL в job `python` — `postgres:15-alpine`, тот же тег, что в compose и манифестах.

## Конфигурация

Основные переменные окружения. Для Docker Compose общие переменные (`SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, пароли баз, `BIND_ADDR`, `CORS_ORIGINS`, `SEED_TEST_USERS`) задаются в корневом `.env`: шаблон — [.env.example](.env.example), создаёт файл `./scripts/init-env.sh`, в git `.env` не попадает. Остальное (адреса сервисов, `GATEWAY_URL` фронтенда, `DATABASE_URL`, который собирается из паролей в `.env`) задано в `docker-compose.yml`. В Kubernetes `SECRET_KEY` берётся из `k8s/overlays/local/app.env` (Secret `app-secrets`), пароли баз — из `db.env` (Secret `db-credentials`), `DATABASE_URL` собирается в манифесте подстановкой `$(DB_PASSWORD)`, а несекретное (`ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, адреса сервисов) лежит в ConfigMap `service-config`. Для запуска без Docker все переменные с описанием собраны в файлах `.env.example` в папке каждого сервиса и в `frontend/login_page`.

| Переменная | Где используется | Описание |
|------------|------------------|----------|
| `DATABASE_URL` | auth, task, time | Строка подключения SQLAlchemy, например `postgresql+psycopg://user:password@host:5432/db` или `sqlite:///./auth.db`. Обязательна: без неё сервис не стартует |
| `SECRET_KEY` | все сервисы | Ключ подписи JWT, должен быть одинаковым везде. Обязателен: без него сервисы не стартуют |
| `ALGORITHM` | все сервисы | Алгоритм подписи, по умолчанию `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | auth | Время жизни access-токена |
| `AUTH_DB_PASSWORD`, `TASK_DB_PASSWORD`, `TIME_DB_PASSWORD` | compose (БД и `DATABASE_URL`) | Пароли баз. Обязательны, генерирует `init-env.sh` |
| `SEED_TEST_USERS` | auth (`python -m app.init_users`) | `true` — команда seed создаёт тестовых пользователей, иначе пропускает их создание. Только для разработки. По умолчанию `false`; в compose задаётся только у `ser-auth-seed`: из `.env` (`true` в шаблоне) или из окружения, дефолт тоже `true` |
| `AUTH_URL`, `TASK_URL`, `TIME_URL` | gateway | Адреса внутренних сервисов |
| `BIND_ADDR` | compose (`ports` у frontend и gateway) | Адрес хоста, на котором публикуются 5173 и 8000. По умолчанию `127.0.0.1` (только эта машина), `0.0.0.0` — все интерфейсы |
| `CORS_ORIGINS` | gateway | Адреса фронтенда, которым разрешены запросы из браузера, через запятую. По умолчанию `http://localhost:5173,http://127.0.0.1:5173`. В Kubernetes — ключ `cors-origins` ConfigMap `service-config`: `http://localhost:8080,http://127.0.0.1:8080` (адрес входа; браузер ходит на один origin, значение нужно для явности и проверки preflight). Внутренние сервисы CORS не настраивают: браузер обращается только к gateway |
| `TIME_SERVICE_URL` | task | Адрес Time Service для сбора статистики |
| `GATEWAY_URL` | frontend (nginx, при запуске контейнера) | Адрес gateway без пути, куда nginx проксирует `/api/`. В compose — `http://ser-gateway:8000`. Имя резолвится при запросах (DNS Docker), поэтому пересоздание gateway не требует перезапуска фронтенда. В Kubernetes — ключ `gateway-url` ConfigMap `service-config`, значение `http://ser-gateway.freelance-service.svc.cluster.local:8000` (полное имя): `resolver` nginx не применяет search-домены из `/etc/resolv.conf`, и короткое `ser-gateway` даёт 502 (`could not be resolved`) |
| `VITE_API_BASE` | frontend (на этапе сборки) | Необязательна. Пусто или не задана — запросы идут на тот же адрес по пути `/api` (в Docker их проксирует nginx, в `npm run dev` — Vite). В образе не задаётся, один образ годится для любого окружения |

`SECRET_KEY` и пароли баз (`AUTH_DB_PASSWORD`, `TASK_DB_PASSWORD`, `TIME_DB_PASSWORD`) в compose обязательны и берутся из `.env`; их генерирует `init-env.sh`. Пароль подставляется в `DATABASE_URL`, поэтому только символы `[A-Za-z0-9_-]` (`@`, `:`, `/` ломают URL). Пароль применяется при создании тома БД: если вы обновились с версии, где пароли были зашиты в compose, один раз выполните `docker compose down -v` (данные при этом удаляются).

## API

Все запросы идут через gateway с префиксом `/api`. Все эндпоинты, кроме `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh` и служебных `/health` и `/` у gateway, требуют заголовок `Authorization: Bearer <access-токен>`.

У проектов и задач в ответах есть `owner_id` — id владельца. Его задаёт сервер: при создании берётся из токена, у задачи в проекте — владелец проекта; поле `owner_id` в теле запроса игнорируется.

Проекты и задачи «только свои»: пользователь в списках видит только свои (фильтры `?project_id=` и `?status=` работают внутри своих), чужой проект или задача для него — `404`, как несуществующие. admin видит и меняет всё. Создать задачу можно только в своём проекте (admin — в любом, задача получает владельца проекта); перенести задачу через `PUT` с `project_id` — только в проект её владельца (user в чужой — `404`, admin — `400`); несуществующий проект, в том числе `project_id=0`, — `404`.

Коды ошибок: без токена, с неверным, просроченным или refresh-токеном вместо access — `401`; не хватает прав (например, не admin) — `403`; неизвестный путь — `404`. Заголовки `X-User-*` от клиента игнорируются.

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/register` | Регистрация |
| POST | `/api/auth/login` | Вход, возвращает access и refresh токены |
| POST | `/api/auth/refresh` | Обновление access-токена |
| GET | `/api/auth/me` | Текущий пользователь |
| GET, POST | `/api/tasks/projects` | Свои проекты (admin — все) и создание проекта |
| GET, PUT, DELETE | `/api/tasks/projects/{id}` | Проект: свой, у admin — любой, чужой — `404` |
| GET, POST | `/api/tasks/tasks` | Свои задачи (admin — все, фильтры `project_id`, `status`) и создание задачи |
| GET, PUT, DELETE | `/api/tasks/tasks/{id}` | Задача: своя, у admin — любая, чужая — `404` |
| POST | `/api/tasks/tasks/{id}/status` | Смена статуса задачи |
| GET | `/api/tasks/statistics/users` | Статистика по пользователям (только admin) |
| GET, POST | `/api/time/time-entries` | Записи о времени: `user_id` берётся из токена; пользователь видит только свои записи, admin — все (фильтр `?user_id=`) |
| GET | `/api/time/statistics/users` | Статистика времени по пользователям (только admin) |

Пример входа:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"password123"}'
```

## Структура репозитория

```
.
├── auth-service/        сервис аутентификации
├── task-service/        проекты и задачи
├── time-service/        учёт времени
├── gateway-service/     API Gateway
├── frontend/login_page/ клиентское приложение (Vue 3)
├── frontend/nginx/      шаблон конфига nginx фронтенда (статика и прокси /api)
├── k8s/                 Kubernetes
│   ├── README.md        инструкция: запуск в kind, диагностика, ограничения
│   ├── base/            манифесты без локальных допущений (kustomize); entrypoint.yaml — вход Gateway + HTTPRoute
│   ├── overlays/local/  overlay для kind: секреты из app.env и db.env, imagePullPolicy, GatewayClass + EnvoyProxy (NodePort 30080)
│   ├── overlays/local-seed/ overlay local + Job auth-seed (тестовые пользователи, применяет k8s-deploy.sh)
│   └── kind-config.yaml конфиг локального кластера kind
├── tests/               сквозные проверки всего стека
│   ├── smoke.sh         curl-прогон через gateway, режимы compose и k8s
│   └── e2e/             e2e в браузере (pytest-playwright): авто-refresh, «только свои»; run.sh — запуск в Docker
├── scripts/             вспомогательные скрипты (init-env.sh — .env, init-k8s-env.sh — секреты кластера, kind-up.sh — кластер kind и образы, k8s-deploy.sh — деплой в кластер)
├── .github/workflows/   CI (GitHub Actions): ci.yml
├── .env.example         шаблон общих переменных для Docker Compose
├── .git-blame-ignore-revs коммиты форматирования, которые пропускает git blame
├── ruff.toml            настройки линтера и форматтера Python (ruff)
└── docker-compose.yml
```

## Текущее состояние

Проект работает как рабочий прототип, но не готов к продакшену. Что уже сделано и какие ограничения предстоит закрыть:

- Gateway проверяет Bearer access-токен (подпись, срок `exp`, тип `access`) для всех путей, кроме `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/health` и `/`. Без токена или с неверным токеном ответ 401, неизвестные пути 404. Клиентские заголовки `X-User-*` затираются, gateway ставит свои `X-User-Id` и `X-User-Role` из токена
- task-service и time-service сами проверяют access-токен так же, как gateway (подпись, `exp`, тип `access`), и не доверяют заголовкам `X-User-*`: без токена 401, в том числе при обращении в обход gateway. Статистика по пользователям только для admin; task-service при сборе статистики передаёт в time-service токен пользователя. В time-service `user_id` записи берётся только из токена (поле `user_id` в теле игнорируется), пользователь видит только свои записи, admin — все
- У проектов и задач есть владелец (`owner_id`, NOT NULL): при создании он берётся из токена, задача в проекте получает владельца проекта. Проекты создают все пользователи. Пользователь видит, меняет и удаляет только свои проекты и задачи (на чужие — 404), admin — все; задача не может оказаться в проекте другого владельца. time-service пока не проверяет, что `task_id` записи времени принадлежит пользователю
- auth-service: роль в access-токене берётся из БД и при входе, и при обновлении токена; отключённый (`is_active=false`) или удалённый пользователь не может войти, обновить токен и получить `/api/auth/me`. Ключ `SECRET_KEY` обязателен. Тестовых пользователей сервис при старте не создаёт: это делает отдельная команда `python -m app.init_users` (в compose — контейнер `ser-auth-seed`) и только при `SEED_TEST_USERS=true`, вывод идёт через logging и виден в `docker logs ser-auth-seed`; в локальном кластере то же делает Job `auth-seed` (`k8s/overlays/local-seed`, в base его нет)
- Python-сервисы в образах работают не от root (пользователь `app`, в Dockerfile `USER 10001` числом — так его проверяет Kubernetes), код в образе доступен только на чтение
- В Kubernetes на namespace приложения включён Pod Security Admission `restricted`: все поды (сервисы, Job, базы) работают не от root (10001 / 101 / 70), без повышения привилегий и capabilities, с seccomp `RuntimeDefault`, корневой файловой системой только на чтение (nginx и postgres пишут в `emptyDir`) и без токена ServiceAccount. Под с нарушением API-сервер не создаёт
- В Docker Compose у auth, task, time и gateway есть healthcheck (`GET /`), у frontend — `GET /` nginx, у баз — `pg_isready` по своей базе, порядок старта задан через `depends_on: service_healthy`: task ждёт time, gateway — три сервиса, frontend — gateway. Полные `/health` и `/ready` с проверкой БД — в планах
- `.dockerignore` исключает `.env`, `*.db`, `.venv`, `node_modules` во всех папках, локальные настройки и базы больше не попадают в образы
- `SECRET_KEY` обязателен во всех сервисах, `DATABASE_URL` обязателен в auth, task и time: значений по умолчанию (в том числе SQLite-файла) нет, без них сервис не стартует. CORS настроен только в gateway и разрешает лишь адреса из `CORS_ORIGINS`
- Фронтенд сам обновляет access-токен: на ответ 401 он один раз запрашивает `/api/auth/refresh` (параллельные запросы ждут один общий refresh) и повторяет запрос. Если refresh не удался, токены удаляются и открывается страница входа. Оба сценария проверяет e2e-тест в браузере (`tests/e2e/`, compose и kind). Refresh-токен живёт 7 дней и не обновляется, после этого нужно войти заново
- Кнопка «Выполнено» в списке задач проекта ставит статус `done`, а не удаляет задачу. Выполненные задачи показываются отдельным сворачиваемым блоком под текущими
- Python 3.14 во всех образах. В Docker Compose и Kubernetes сервисы работают с PostgreSQL через psycopg 3 (`postgresql+psycopg://`). Зависимости бэкенда ведёт uv: прямые закреплены точными версиями (`==`) в `pyproject.toml` сервиса, все вместе с транзитивными — в `uv.lock` (версии и хеши), общие пакеты одинаковы во всех сервисах. Образ ставит их `uv sync --locked` (сборка падает, если `uv.lock` не совпадает с `pyproject.toml`) в `/opt/venv`; сам uv в итоговый образ не попадает. `pytest`, `httpx2` и `pytest-cov` — в dev-группе, в образ не ставятся
- Схема БД auth-service, task-service и time-service управляется миграциями Alembic (`<service>/migrations/`): в Docker Compose их применяют сервисы `ser-auth-migrate`, `ser-task-migrate` и `ser-time-migrate` до старта своего сервиса, в Kubernetes — Job `auth-migrate`, `task-migrate`, `time-migrate` (один раз на деплой, порядок задаёт `scripts/k8s-deploy.sh`). Тест в каждом из них проверяет, что миграции совпадают с моделями
- Проекты хранятся только в task-service: дубль проектов в time-service (`/api/time/projects`) удалён, фронтенд создаёт проект одним запросом. `user_id` записи времени обязателен (NOT NULL), фронтенд его не отправляет: сервер берёт `user_id` из токена
- Автотесты (pytest) есть у всех бэкенд-сервисов (с PostgreSQL: gateway 51, auth 36, task 54, time 32; без `TEST_POSTGRES_URL` тесты миграций на PostgreSQL пропускаются — 51 / 34 + 2 skipped / 51 + 3 skipped / 30 + 2 skipped), покрытие 100 / 93 / 97 / 99 % с порогом в `pyproject.toml`. Python-код проверяет ruff (`ruff.toml`, см. «Линтер»), типы фронтенда — `npm run typecheck` (vue-tsc, 0 ошибок). Сквозные проверки: smoke (`tests/smoke.sh`, compose 116, k8s 114) и e2e в браузере (`tests/e2e/`, 3 теста: авто-refresh, неудачный refresh, «только свои»). Всё это, а также shellcheck, gitleaks, kubeconform и сквозные прогоны в compose и kind с нуля, выполняет CI (GitHub Actions) на каждый push и pull request (см. «CI»)
- Фронтенд в Docker собирается multi-stage на Node 24 (`npm ci`, `vite build`) и раздаётся nginx без root (`nginx-unprivileged`, слушает 8080): долгий кэш для `/assets/`, `index.html` без кэша, gzip, SPA-роуты отдают `index.html`. Запросы `/api/` nginx проксирует на gateway, поэтому браузер ходит на один адрес и CORS для фронтенда не нужен. В Kubernetes фронтенд описан под этот образ: порт 8080, `GATEWAY_URL` из ConfigMap, startup/liveness/readiness `GET /`, Service `ClusterIP`
- В Kubernetes вход один — Gateway API (Envoy Gateway v1.9.2) на `http://127.0.0.1:8080`: `/api` → gateway, остальное → фронтенд; `LoadBalancer` и `NodePort` в namespace приложения нет, все сервисы `ClusterIP`. Автомасштабирования нет: у stateless-сервисов (auth, task, time, gateway, frontend) по две реплики, базы — по одной. При `rollout restart` под нагрузкой возможны единичные 502/503 в момент остановки старого пода (graceful shutdown — в планах). Кластер — только локальный kind (`./scripts/kind-up.sh`, ставит и Envoy Gateway), манифесты собираются kustomize (`base` + `overlays/local`), деплой с миграциями и seed — `./scripts/k8s-deploy.sh`; проверено с нуля (инструкция и ограничения — [k8s/README.md](k8s/README.md)). Облачного overlay (реестр образов, TLS, управляемый Postgres) нет. Базы в кластере проверяются `pg_isready -U … -d …`, `PGDATA` лежит в подпапке тома. Readiness сервисов — публичный `GET /`, без проверки БД
- В Kubernetes сетевые политики по умолчанию запрещают всё: открыты только DNS, вход от Envoy к фронту и gateway, фронт → gateway, gateway → auth, task, time, task → time и каждый сервис со своими Job → своя база. Сервис не достанет до чужой базы, базы и сервисы не выходят в интернет ([k8s/README.md](k8s/README.md#сетевые-политики))
- Нет пагинации, фильтрации и сортировки задач
- В Docker Compose наружу опубликованы только frontend (5173) и gateway (8000), по умолчанию на `127.0.0.1` (`BIND_ADDR`); auth, task, time и базы доступны только внутри сети compose
- Секреты и пароли баз в Docker Compose генерирует `scripts/init-env.sh` (в `.env`, не в git); в Kubernetes секреты лежат в `k8s/overlays/local/app.env` и `db.env` (генерирует `scripts/init-k8s-env.sh`, не в git), пароли в манифестах не зашиты

## Планы

- Серверное состояние таймера: запуск, пауза и остановка на бэкенде, защита от параллельных таймеров
- Kubernetes: graceful shutdown (`preStop`) для rollout без 502/503; readiness на `/ready` с проверкой БД и ревизии схемы; позже — облачный overlay и HPA
- Отчёты по времени и экспорт
- Лимиты запросов, логирование, метрики

## Лицензия

Лицензия пока не выбрана.
