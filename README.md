# Freelance Time Tracker

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
- Vue 3, TypeScript, Pinia, Vue Router, Axios, Vite, Naive UI
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

Нужны [uv](https://docs.astral.sh/uv/) (проверено на 0.13.1) и Node.js 20+. Python 3.14 (версия в `.python-version`) uv при необходимости скачает сам. Каждый сервис запускается в отдельном терминале со своим виртуальным окружением: `uv sync` создаёт `.venv` в папке сервиса и ставит в него зависимости строго по `uv.lock` (вместе с dev-группой для тестов), `uv run <команда>` выполняет команду в этом окружении, активировать его не нужно. Окружение `.venv`, созданное раньше через `python -m venv` с другой версией Python, uv пересоздаст сам. Добавить или обновить зависимость — `uv add 'пакет==версия'` в папке сервиса (меняет `pyproject.toml` и `uv.lock`, оба файла коммитятся вместе). В auth-service, task-service и time-service таблицы создаёт `uv run alembic upgrade head` (выполнить перед первым запуском и после обновления кода). Если `auth.db`, `task.db` или `time_service.db` осталась от версии без миграций, удалите её: на таблицах, созданных без Alembic, `alembic upgrade head` падает с ошибкой вида `table users already exists`. Базу выбирает обязательная переменная `DATABASE_URL`: для локального запуска в `.env.example` указан SQLite-файл в папке сервиса.

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

Фронтенд обращается к API по относительному пути `/api`: `npm run dev` проксирует его на gateway `http://localhost:8000` (`server.proxy` в `vite.config.ts`), браузер остаётся на одном адресе, CORS не участвует. Переменная `VITE_API_BASE` в `frontend/login_page/.env` необязательна: задавайте её, только если фронтенд должен ходить на gateway напрямую, и тогда добавьте адрес фронтенда в `CORS_ORIGINS` gateway. Если в вашем `.env` осталась старая строка `VITE_API_BASE=http://localhost:8000`, уберите её, чтобы запросы шли через прокси.

### Тесты

Тесты есть у gateway, auth-service, task-service и time-service. Им не нужны запущенные сервисы: внешние HTTP-вызовы (gateway → сервисы, task → time) подменяются в тестах, базы — временная SQLite. Запуск в папке сервиса (`<service>` — `gateway-service`, `auth-service`, `task-service` или `time-service`):

```bash
cd <service>
uv run pytest -q
```

uv сам поставит Python 3.14 и зависимости из `uv.lock` вместе с dev-группой (`pytest`, `httpx2` — клиент для `TestClient` Starlette, `pytest-cov`). Покрытие: `uv run pytest --cov=app`.

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
├── tests/               сквозные проверки всего стека (smoke.sh — curl-прогон через gateway, режимы compose и k8s)
├── scripts/             вспомогательные скрипты (init-env.sh — .env, init-k8s-env.sh — секреты кластера, kind-up.sh — кластер kind и образы, k8s-deploy.sh — деплой в кластер)
├── .env.example         шаблон общих переменных для Docker Compose
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
- Фронтенд сам обновляет access-токен: на ответ 401 он один раз запрашивает `/api/auth/refresh` (параллельные запросы ждут один общий refresh) и повторяет запрос. Если refresh не удался, токены удаляются и открывается страница входа. Refresh-токен живёт 7 дней и не обновляется, после этого нужно войти заново
- Кнопка «Выполнено» в списке задач проекта ставит статус `done`, а не удаляет задачу. Выполненные задачи показываются отдельным сворачиваемым блоком под текущими
- Python 3.14 во всех образах. В Docker Compose и Kubernetes сервисы работают с PostgreSQL через psycopg 3 (`postgresql+psycopg://`). Зависимости бэкенда ведёт uv: прямые закреплены точными версиями (`==`) в `pyproject.toml` сервиса, все вместе с транзитивными — в `uv.lock` (версии и хеши), общие пакеты одинаковы во всех сервисах. Образ ставит их `uv sync --locked` (сборка падает, если `uv.lock` не совпадает с `pyproject.toml`) в `/opt/venv`; сам uv в итоговый образ не попадает. `pytest`, `httpx2` и `pytest-cov` — в dev-группе, в образ не ставятся
- Схема БД auth-service, task-service и time-service управляется миграциями Alembic (`<service>/migrations/`): в Docker Compose их применяют сервисы `ser-auth-migrate`, `ser-task-migrate` и `ser-time-migrate` до старта своего сервиса, в Kubernetes — Job `auth-migrate`, `task-migrate`, `time-migrate` (один раз на деплой, порядок задаёт `scripts/k8s-deploy.sh`). Тест в каждом из них проверяет, что миграции совпадают с моделями
- Проекты хранятся только в task-service: дубль проектов в time-service (`/api/time/projects`) удалён, фронтенд создаёт проект одним запросом. `user_id` записи времени обязателен (NOT NULL), фронтенд его не отправляет: сервер берёт `user_id` из токена
- Автотесты (pytest) есть у всех бэкенд-сервисов (gateway 45, auth 34, task 51, time 25), CI нет.
- Фронтенд в Docker собирается multi-stage (`npm ci`, `vite build`) и раздаётся nginx без root (`nginx-unprivileged`, слушает 8080): долгий кэш для `/assets/`, `index.html` без кэша, gzip, SPA-роуты отдают `index.html`. Запросы `/api/` nginx проксирует на gateway, поэтому браузер ходит на один адрес и CORS для фронтенда не нужен. В Kubernetes фронтенд описан под этот образ: порт 8080, `GATEWAY_URL` из ConfigMap, startup/liveness/readiness `GET /`, Service `ClusterIP`
- В Kubernetes вход один — Gateway API (Envoy Gateway v1.9.2) на `http://127.0.0.1:8080`: `/api` → gateway, остальное → фронтенд; `LoadBalancer` и `NodePort` в namespace приложения нет, все сервисы `ClusterIP`. Автомасштабирования нет: у stateless-сервисов (auth, task, time, gateway, frontend) по две реплики, базы — по одной. При `rollout restart` под нагрузкой возможны единичные 502/503 в момент остановки старого пода (graceful shutdown — в планах). Кластер — только локальный kind (`./scripts/kind-up.sh`, ставит и Envoy Gateway), манифесты собираются kustomize (`base` + `overlays/local`), деплой с миграциями и seed — `./scripts/k8s-deploy.sh`; проверено с нуля (инструкция и ограничения — [k8s/README.md](k8s/README.md)). Облачного overlay (реестр образов, TLS, управляемый Postgres) нет. Базы в кластере проверяются `pg_isready -U … -d …`, `PGDATA` лежит в подпапке тома. Readiness сервисов — публичный `GET /`, без проверки БД
- В Kubernetes сетевые политики по умолчанию запрещают всё: открыты только DNS, вход от Envoy к фронту и gateway, фронт → gateway, gateway → auth, task, time, task → time и каждый сервис со своими Job → своя база. Сервис не достанет до чужой базы, базы и сервисы не выходят в интернет ([k8s/README.md](k8s/README.md#сетевые-политики))
- Нет пагинации, фильтрации и сортировки задач
- В Docker Compose наружу опубликованы только frontend (5173) и gateway (8000), по умолчанию на `127.0.0.1` (`BIND_ADDR`); auth, task, time и базы доступны только внутри сети compose
- Секреты и пароли баз в Docker Compose генерирует `scripts/init-env.sh` (в `.env`, не в git); в Kubernetes секреты лежат в `k8s/overlays/local/app.env` и `db.env` (генерирует `scripts/init-k8s-env.sh`, не в git), пароли в манифестах не зашиты

## Планы

- Серверное состояние таймера: запуск, пауза и остановка на бэкенде, защита от параллельных таймеров
- CI: тесты, линтер, сборка фронтенда, сквозной smoke-прогон через gateway
- Kubernetes: graceful shutdown (`preStop`) для rollout без 502/503; readiness на `/ready` с проверкой БД и ревизии схемы; кластер kind в CI; позже — облачный overlay и HPA
- Отчёты по времени и экспорт
- Лимиты запросов, логирование, метрики

## Лицензия

Лицензия пока не выбрана.
