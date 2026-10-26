# Freelance Time Tracker

[![CI](https://github.com/vadim-white/application-for-freelancers/actions/workflows/ci.yml/badge.svg)](https://github.com/vadim-white/application-for-freelancers/actions/workflows/ci.yml)

Трекер задач и рабочего времени на микросервисной архитектуре. Бэкенд написан на FastAPI, фронтенд на Vue 3. Проект задуман как полноценная open-source альтернатива готовым решениям на Django: с раздельными сервисами, единой точкой входа и деплоем в контейнерах и Kubernetes.

Проект находится в активной разработке. Раздел [Текущее состояние](#текущее-состояние) описывает, что уже работает, а что ещё нет.

## Возможности

- Регистрация и вход по email и паролю, JWT (access и refresh токены), роли `user` и `admin`
- Проекты и задачи: создание, просмотр, смена статуса, архив и восстановление; списки по страницам с сортировкой и фильтрами. Правка в окнах «Изменить» (задача: название, описание, срок, статус, проект; проект: название, описание); задачи вне проекта — в карточке «Без проекта» первой на дашборде (та же панель, задачу можно создать без проекта и вынести из проекта окном «Изменить»); удаление — только через API (в интерфейсе — архив: удаление проекта удаляет и его задачи). Пользователь работает только со своими проектами и задачами, администратор — со всеми
- Таймер на задачу хранится на сервере: старт, пауза (останавливает таймер и сохраняет запись времени), «Продолжить» (новая запись на ту же задачу), запись любой длины. Идущий таймер переживает перезагрузку страницы и виден на дашборде (задача и время, клик открывает окно таймера); у пользователя один таймер — старт на другой задаче останавливает идущий. Остановка не помечает задачу выполненной: для этого отдельная кнопка «Выполнена», а старт переводит задачу из «К выполнению» в «В работе»
- Статистика по пользователям для администратора: число записей и задач, затраченное время всего и в среднем на задачу
- Страница пользователей для администратора (`/users`): таблица, фильтры по роли и статусу, поиск по email и имени, страницы, смена роли и отключение или включение пользователя
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

У каждого сервиса своя база данных, сервисы не ходят в чужие таблицы. Между собой ходят по HTTP два сервиса: Task Service берёт у Time Service статистику, а Time Service перед стартом таймера, ручной записью и сменой задачи в записи спрашивает у Task Service задачу. Вызовы не вложены друг в друга.

Gateway держит один HTTP-клиент на процесс (`httpx.AsyncClient`, пул keep-alive соединений к сервисам; создаётся при старте и закрывается при остановке). Таймауты запроса к сервису: подключение 5 с, остальное 30 с. Сервис недоступен (отказ в соединении, имя не резолвится, разрыв) — 502 `Upstream service unavailable`, сервис не ответил вовремя — 504 `Upstream service timeout`; причина пишется в лог gateway. Если соединение оборвалось до ответа (например, его закрыл останавливающийся под сервиса), идемпотентный запрос (GET, OPTIONS, PUT, DELETE) повторяется один раз, POST и PATCH — нет: они могли дойти до сервиса. Тело ответа идёт клиенту потоком, байты как есть (сжатое — вместе с `content-encoding`). Hop-by-hop заголовки (`connection`, `keep-alive`, `te`, `trailer`, `transfer-encoding`, `upgrade`, `proxy-*` и перечисленные в `Connection`) gateway не пересылает ни в запросе, ни в ответе, а `date` и `server` в ответе ставит сам uvicorn gateway — копии от сервиса отбрасываются. `/health` опрашивает три сервиса параллельно, с таймаутом 2 с на каждый. Готовность к трафику — `GET /ready`: у auth, task и time он проверяет базу и ревизию схемы, у gateway всегда 200 (см. «Текущее состояние»).

Простаивающее keep-alive соединение закрывает тот, кто шлёт по нему запросы, а не сервер: иначе запрос может уйти в соединение, которое сервер как раз закрывает, и оборвётся (POST и PATCH никто не повторяет). Поэтому uvicorn у всех четырёх сервисов держит простаивающее соединение 75 с (`--timeout-keep-alive 75` в Dockerfile), а клиенты закрывают раньше: httpx (gateway → сервисы, task ↔ time) — через 5 с (умолчание), Envoy на входе kind — через 60 с (`BackendTrafficPolicy` `entry`, без неё Envoy держит соединение 1 час); nginx фронта держит 65 с, тоже больше 60. Так же настраивают сервер за облачным балансировщиком (ALB 60 с → сервер 65+ с).

В Kubernetes вход в кластер один — Gateway API (контроллер Envoy Gateway) на `http://127.0.0.1:8080`: `/api` уходит в API Gateway, всё остальное — во фронтенд. Сервисы приложения наружу не публикуются (все `ClusterIP`):

```
   Браузер → 127.0.0.1:8080 → Envoy (Gateway "entry", HTTPRoute "entry-routes")
                                 /api/*  → ser-gateway:8000 → auth, task, time
                                 /*      → ser-frontend:8080 (статика; его /api/ тоже проксируется на gateway)
```

## Стек

- Python 3.14, FastAPI 0.160, SQLAlchemy 2.1 (модели на `Mapped[]`), Pydantic 2, драйвер PostgreSQL psycopg 3
- uv — зависимости Python (`pyproject.toml` + `uv.lock` в каждом сервисе), pytest
- PostgreSQL 15 (в Docker), SQLite для локальной разработки без контейнеров
- JWT (PyJWT), хеширование паролей — pwdlib с bcrypt
- Vue 3.5, TypeScript 5.9, Pinia 2, Vue Router 4, Axios 1, Vite 5, Naive UI 2; Node.js 24 (сборка фронтенда), проверка типов — vue-tsc
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

`--wait` возвращает управление, когда одноразовые контейнеры (миграции, seed) завершились с кодом 0, а auth, task, time, gateway, frontend и базы стали `healthy` (у auth, task и time проверка — `GET /ready`: база доступна и схема на месте, у gateway — `GET /ready`, у frontend — `GET /`, у баз — `pg_isready`). Поэтому сразу после команды можно входить под тестовыми пользователями. Без `--wait` стек тоже поднимется, но сервисы ещё какое-то время будут стартовать. Нужен Docker Compose v2 (проверено на 2.40.2, в CI — 2.38.2).

Без `.env` `docker compose` не стартует и пишет «задайте в .env (./scripts/init-env.sh)». Скрипт создаёт корневой `.env` из `.env.example`; если `.env` уже есть, дописывает только отсутствующие ключи, существующие значения не трогает. Значения секретов он не печатает. Секреты генерирует `python3` или `openssl`; если нет ни того ни другого, скрипт печатает «Нужен python3 или openssl для генерации секретов» и завершается с кодом 1, пустые значения в `.env` не пишутся.

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

`down -v`, как и `up`, читает `.env` и без него не запускается. Чтобы начать с новыми секретами, сначала выполните `docker compose down -v`, затем удалите `.env` и запустите `./scripts/init-env.sh`. Если удалить `.env` раньше, тома со старыми паролями останутся, и миграции упадут с `password authentication failed`.

### Локальный запуск без Docker

Нужны [uv](https://docs.astral.sh/uv/) (проверено на 0.13.5) и Node.js 24 (версия в `frontend/login_page/.nvmrc`). Python 3.14 (версия в `.python-version`) uv при необходимости скачает сам. Каждый сервис запускается в отдельном терминале со своим виртуальным окружением: `uv sync` создаёт `.venv` в папке сервиса и ставит в него зависимости строго по `uv.lock` (вместе с dev-группой для тестов), `uv run <команда>` выполняет команду в этом окружении, активировать его не нужно. Окружение `.venv`, созданное раньше через `python -m venv` с другой версией Python, uv пересоздаст сам. Добавить или обновить зависимость — `uv add 'пакет==версия'` в папке сервиса (меняет `pyproject.toml` и `uv.lock`, оба файла коммитятся вместе). В auth-service, task-service и time-service таблицы создаёт `uv run alembic upgrade head` (выполнить перед первым запуском и после обновления кода). Если `auth.db`, `task.db` или `time_service.db` осталась от версии без миграций, удалите её: на таблицах, созданных без Alembic, `alembic upgrade head` падает с ошибкой вида `table users already exists`. Базу выбирает обязательная переменная `DATABASE_URL`: для локального запуска в `.env.example` указан SQLite-файл в папке сервиса.

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

Приложение открывается на http://localhost:5173 (адрес печатает `npm run dev`). Тестовых пользователей рецепт не создаёт: зарегистрируйтесь в приложении или впишите в `auth-service/.env` `SEED_TEST_USERS=true` и выполните там `uv run python -m app.init_users`. Рецепт целиком (свежий клон, `.env` из примеров, SQLite, `npm run dev`) проверен на чистом Linux в контейнерах `uv` и `node:24-alpine` с общим `localhost`: регистрация и вход, проект, задача, старт и стоп таймера, статистика admin после seed.

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

На тех же двух базах идут тесты `/ready` (`tests/test_ready.py`): схема на head → 200; пустая база и база после `downgrade base` → 503; ревизия — предок head → 503 (в time — настоящие ревизии до expand, до contract и до удаления старых колонок; в auth и task по одной ревизии, поэтому цепочка «текущий head — предок нового» подставляется в тесте); незнакомая ревизия (`UPDATE alembic_version`) → 200; база недоступна → 503. Без PostgreSQL: «молчащая» база (порт принимает TCP и не отвечает) даёт 503 раньше таймаута пробы (`connect_timeout` 2 с), а head и его предки берутся из цепочки `down_revision` (временный каталог с тремя ревизиями). Фикстура пустой базы `migrations_db` общая для обоих файлов — в `tests/conftest.py`.

Таймауты к базе на открытом соединении проверяются только на PostgreSQL (фикстура `pg_app` в `tests/conftest.py`: движок как в приложении, `make_engine`, своя схема на head, через него идут сессии API и `/ready`): `SELECT pg_sleep(10)` обрывается `statement_timeout` за ~5 с, `/ready`, ждущий блокировку `alembic_version`, отвечает 503 за ~5 с, а не висит; после `pg_terminate_backend` соединений пула (как перезапуск базы) следующий запрос API — 200 (`pool_pre_ping`). Без базы: параметры соединения из `connect_args` принимает libpq (опечатка в имени не ждёт первого соединения).

Таймер time-service (`tests/test_timer.py`): старт, стоп, повторный стоп, повторный старт той же задачи, автостоп, длительность (округление вниз, запись 0 с), свой таймер у каждого и у admin, поля записи в ответе; уникальный индекс «один идущий» — на SQLite и PostgreSQL; на PostgreSQL — гонка двух стартов (два соединения: второй ждёт первый на индексе, получает конфликт, повторяет и закрывает его запись). Миграции time (`test_migrations.py`) на SQLite и PostgreSQL: expand заполняет старые записи (`started_at`, `stopped_at`, `duration_seconds` из `date` и `minutes`); contract дозаполняет записи старых подов из окна expand, ставит `started_at NOT NULL`, индекс идущего таймера — `WHERE stopped_at IS NULL`, `is_active` по умолчанию `true` и откатывается до expand; удаление `minutes`, `date`, `is_active` — колонок на head нет, CHECK и частичный индекс пережили пересоздание таблицы на SQLite, откат возвращает колонки nullable (`date` у старых строк пустой, `is_active` — `true`); на head CHECK, `NOT NULL` и индекс отклоняют неверные строки (`IntegrityError`). Только на PostgreSQL: если таблицу держит долгая транзакция, contract и удаление колонок через 3 с сдаются (`lock_timeout`), а не ждут.

Записи времени time-service (`tests/test_time.py`): ручная запись (длительность считает сервер, время с поясом, `stopped_at` раньше `started_at` и будущее — 422, чужая или архивная задача — через мок task), список (конверт, фильтры `task_id`, `from`, `to`, сортировка, пагинация, 422 на неверные параметры), `PATCH` (пересчёт `duration_seconds`, неизвестное поле и `user_id` в теле — 422 без изменений записи, чужая запись — 404, admin правит любую, задача проверяется, только если `task_id` есть в теле, `stopped_at` у идущей — 422), `DELETE` (в том числе идущей), статистика (поля, `distinct` по задачам, идущие записи не считаются); список и статистика проверены и на PostgreSQL. В task-service один `httpx.AsyncClient` из lifespan для статистики проверен отдельным тестом.

Каждый тест работает в собственной схеме (`CREATE SCHEMA mig_…` или `app_…` / `DROP SCHEMA … CASCADE` после теста), поэтому база может быть общей для трёх сервисов; важно только, чтобы это была тестовая база, а не база стека. Локально:

```bash
docker run --rm -d --name pg-test -p 127.0.0.1:55432:5432 -e POSTGRES_PASSWORD=test postgres:15-alpine
cd task-service                          # или auth-service, time-service
TEST_POSTGRES_URL=postgresql+psycopg://postgres:test@127.0.0.1:55432/postgres uv run pytest -q -rs
docker stop pg-test
```

Тесты в контейнере (рецепт Docker выше) подключаются к PostgreSQL по имени в общей сети: `docker network create t15`, `docker run -d --rm --network t15 --name pg -e POSTGRES_PASSWORD=test postgres:15-alpine`, затем в команду тестов добавить `--network t15 -e TEST_POSTGRES_URL=postgresql+psycopg://postgres:test@pg:5432/postgres`. После проверки: `docker stop pg && docker network rm t15`.

#### Покрытие

`uv run pytest --cov=app --cov-report=term-missing` печатает покрытие и непокрытые строки. Порог — `[tool.coverage.report] fail_under` в `pyproject.toml` сервиса (gateway 98 %, auth 91 %, task 95 %, time 97 %, чуть ниже фактического 100 / 97,2 / 100 / 99,7 %); он срабатывает только при запуске с `--cov`. В `addopts` `--cov` не добавлен: обычный `uv run pytest` и прогон одного файла от порога не зависят. Порог защищает от падения покрытия, гнаться за 100 % не нужно.

Без uv на машине — в Docker, в официальном образе uv с Python 3.14 на том же Debian, что и `python:3.14-slim` у сервисов:

```bash
docker run --rm -v "$PWD/<service>":/src:ro ghcr.io/astral-sh/uv:0.13.5-python3.14-trixie-slim sh -c \
  "cp -r /src /app && cd /app && rm -rf .env .venv && uv run --locked pytest -q"
```

#### Сквозной прогон

[tests/smoke.sh](tests/smoke.sh) — curl-прогон через gateway: авторизация, доступ «только свои», записи времени, таймер, `/health`, CORS. Идемпотентен, проходит на чистой базе и повторно. Готовности стека не ждёт.

```bash
docker compose up --build -d --wait
bash tests/smoke.sh                      # режим compose: 181 проверка

./scripts/k8s-deploy.sh                  # кластер kind (см. k8s/README.md)
SMOKE_MODE=k8s bash tests/smoke.sh       # режим k8s: 179 проверок через http://127.0.0.1:8080
```

`/health` gateway всегда отвечает 200, а доступность сервисов пишет в теле (`upstreams`), поэтому smoke проверяет тело: `auth`, `task`, `time` — все `true`. В k8s запрос идёт изнутри пода `ser-gateway` (через вход `/health` отдаёт фронт). `/ready` auth, task и time проверяется изнутри gateway в обоих режимах: он вне `/api`, через gateway недоступен. Каждый запрос curl ограничен 15 с (`--max-time`), молчащий сервер не повесит прогон. Проксированный ответ проверяется на один заголовок `date` (раньше gateway пересылал ещё и `date` сервиса). В конце smoke сверяет число пройденных проверок с ожидаемым (181 / 179): пропущенная проверка (например, пустой цикл) не даёт FAIL, но и не даёт PASS, и тогда печатается «пройдено N из ожидаемых M». Код выхода 0 — FAIL нет и пройдено ровно ожидаемое число.

smoke меняет seed-пользователя user1: admin отключает его через `PATCH /api/auth/users/{id}` и сразу включает обратно. Если прогон оборвётся между этими запросами, user1 останется отключённым и следующий прогон упадёт на входе; включить — `PATCH /api/auth/users/{id}` с `{"is_active": true}` от admin (повторный seed не поможет: существующих он не трогает). Пользователя, которого прогон регистрирует сам, smoke повышает до admin, затем понижает и отключает, чтобы admin в базе не копились между прогонами; строки журнала прав (`user_audit`) проверяет через `psql` в базе auth.

Счётчик неудачных входов smoke проверяет только на адресах прогона: зарегистрированный `e2e-adm-…` и незарегистрированный `nobody-…` — пять неверных паролей → 401, шестой → 429 с `Retry-After` от 1 до 900, верный пароль в окне → 429. Эти адреса остаются запертыми 15 минут, повторный прогон берёт новые. Две неудачи user1 выше по прогону обнуляет его успешный вход; seed-пользователей smoke не запирает. Если прогон оборвётся между ними, счётчик user1 истечёт сам через 15 минут.

#### e2e в браузере (Playwright)

[tests/e2e/](tests/e2e/) — тесты фронтенда в headless Chromium (pytest-playwright), вход через форму, как у пользователя:

- **авто-refresh**: на `/dashboard` `access_token` заменяется на `abc` и страница перезагружается. Дашборд шлёт параллельные запросы (два `GET /api/auth/me`), оба получают 401, ожидается ровно один `POST /api/auth/refresh` (200). Затем каждый упавший запрос повторяется с 200, страница остаётся на `/dashboard`;
- **неудачный refresh**: подменены оба токена, ожидается один refresh с 401. Токены удаляются из `localStorage`, открывается `/login`;
- **«только свои»**: user1 создаёт проект через UI (имя с меткой прогона). user2 не видит его ни в `GET /api/tasks/projects`, ни на странице, а по id получает 404. admin видит проект;
- **счётчик задач**: user1 создаёт проект и 4 задачи через API, после перезагрузки дашборда в карточке проекта счётчик «(4)», а показаны первые три задачи; за вход и перезагрузку ровно по одному `GET /api/tasks/tasks` (только `project_id=none` — карточка «Без проекта»), задач по проектам дашборд не запрашивает (превью и счётчик приходят в списке проектов);
- **стартовый роут**: без входа `/` открывает `/login`; после входа `/`, `/login` и `/register` ведут на `/dashboard`;
- **таймер переживает перезагрузку**: старт в окне задачи, перезагрузка страницы — `GET /api/time/timer` возвращает идущую запись, индикатор на дашборде показывает задачу и время, по клику открывается окно, «Пауза» останавливает таймер;
- **короткая запись и заметка**: таймер идёт 6 с, «Пауза» — стоп 200, `duration_seconds` ≥ 5, ответов 422 нет (раньше запись короче 30 с уходила как `minutes: 0` и получала 422); заметку можно менять во время работы и после стопа — окно шлёт `PATCH` записи, в списке остаётся последний текст;
- **стоп не ставит `done`**: старт переводит задачу из `todo` в `in_progress` (`PATCH` задачи), после «Паузы» статус по-прежнему `in_progress` — в окне и в API;
- **время задачи А не пишется в Б**: таймер на А, окно закрыто, то же окно открыто для Б — у Б `00:00:00`, «Пауза» недоступна, видно, что идёт А; старт Б останавливает А (тост, `stopped` в ответе), у каждой задачи ровно одна запись, запись Б начинается не раньше конца записи А.
- **/users закрыта для user**: user1 не видит кнопку «Пользователи», прямой переход на `/users` ведёт на `/dashboard`, список пользователей не запрашивается;
- **admin отключает и включает пользователя**: тест регистрирует пользователя через API, admin открывает `/users` кнопкой в шапке, находит его поиском по email (в таблице одна строка), «Отключить» — `PATCH` 200, вход этого пользователя через API — 403; «Включить» — вход снова 200. У строки самого admin кнопок действий нет. Seed-пользователей тест не меняет (на них опираются остальные тесты и smoke).
- **email в статистике**: тест создаёт user1 проект, задачу и запись времени через API, admin открывает «Статистику» — в таблице ровно одна строка с `user1@example.com`, запросы `GET /api/auth/users` с 200;
- **роль после смены**: пользователь теста входит как user (кнопки «Статистика» нет), admin повышает его через API, после перезагрузки страницы — один `POST /api/auth/refresh` (200), «Статистика» видна, `GET /api/tasks/statistics/users` — 200, ответов 403 нет. В конце пользователь снова user и отключён;
- **архив проекта**: проект user1 (создан через API) уходит кнопкой «В архив» — `PATCH` 200, карточка пропадает с дашборда; «Показать архив» показывает его, «Восстановить» возвращает; выбор сортировки «Название А–Я» уходит в запрос (`sort=name`);
- **архив задачи**: задача в панели проекта уходит в архив — пропадает из панели, а в карточке проекта счётчик и превью перечитаны (задач нет); в архиве у неё нет кнопок таймера и «Выполнена», «Восстановить» возвращает её с кнопкой таймера;
- **страницы и сортировка панели**: в проекте 21 задача (создана через API) — на первой странице «Текущих» 20, на второй одна; сортировка «Название Я–А» возвращает на первую страницу и переворачивает порядок;
- **правка задачи**: на задаче идёт таймер; в окне «Изменить» меняются название, срок (введён в поле) и статус «Заблокирована» — `PATCH` 200 с телом ровно из `title`, `deadline` (с `Z`) и `status`, описание не уходит; в строке задачи новое название, статус и срок, в API те же значения, а индикатор таймера показывает новое название;
- **очистка и «без изменений»**: «Сохранить» без правок закрывает окно без `PATCH`; название из пробелов — тост «Введите название задачи», окно остаётся, запроса нет; очищенное описание уходит как `{"description": null}`, в API `description: null`, название прежнее;
- **перенос задачи**: в окне выбран другой проект — `PATCH` с одним `project_id`; задача пропала из панели первого проекта, в карточке первого задач нет, в карточке второго одна «(1)»;
- **правка у admin**: admin открывает задачу user1 — в списке проектов окна есть второй проект user1 и нет проекта user2; перенос — `PATCH` 200 (не 400);
- **правка проекта**: «Изменить» на карточке — `PATCH` только с `name`, на карточке новое имя; проект уходит в архив, в режиме «Показать архив» его переименование снова шлёт только `name`, проект остаётся в архиве (`is_active: false` в API);
- **задача без проекта**: в панели карточки «Без проекта» (заголовок «📋 Без проекта») user1 добавляет задачу — `POST` без `project_id`, в ответе и в API `project_id: null`, на карточке счётчик «до → после» (до — из API; архивная задача вне проекта в него не входит); на ней стартует таймер (201). admin открывает ту же панель и видит задачу user1; его «Добавить задачу» создаёт задачу admin (другой `owner_id`). Задачи вне проекта копятся у user1 между прогонами, поэтому проверки идут по названию в панели («новые сверху») и по счётчику «до → после»;
- **вынос задачи из проекта**: в окне «Изменить» выбран «Без проекта» — `PATCH {"project_id": null}`; задача пропала из панели проекта, в карточке проекта задач нет, счётчик карточки «Без проекта» вырос на единицу; в её панели задача есть, в окне правки выбран «Без проекта».

В каждом тесте проверяется, что все запросы страницы идут на тот же origin, что и фронт. Тесты создают только свои объекты (метка `e2e-<время>-<случайное>`), seed-пользователи те же, что у smoke. Стек должен быть уже поднят: скрипт его не запускает.

```bash
docker compose up --build -d --wait
bash tests/e2e/run.sh                                       # compose: http://127.0.0.1:5173 (по умолчанию)
E2E_BASE_URL=http://127.0.0.1:8080 bash tests/e2e/run.sh    # кластер kind, через вход
bash tests/e2e/run.sh -k refresh -v                         # аргументы передаются pytest
```

`run.sh` собирает образ `freelance-e2e` из [tests/e2e/Dockerfile](tests/e2e/Dockerfile) и запускает в нём pytest. База — `mcr.microsoft.com/playwright/python:v1.64.1-noble` (браузеры, Python 3.12). Python-зависимости ставятся `uv sync --locked` строго по `tests/e2e/uv.lock`, uv берётся бинарником из `ghcr.io/astral-sh/uv:0.13.5`. Оба образа закреплены по digest. Версия пакета `playwright` (1.64.1) равна версии образа. Сеть:
- **macOS** (Docker Desktop): host-сети нет, порты стека опубликованы на `127.0.0.1` хоста. Внутри контейнера поднимается TCP-форвардер `127.0.0.1:<порт>` → `host.docker.internal:<порт>` ([forward.py](tests/e2e/forward.py)), и браузер открывает тот же адрес, что и на хосте;
- **Linux**: `docker run --network host`, форвардер не нужен.

Порт берётся из `E2E_BASE_URL`. Скриншот и trace упавшего теста сохраняются в `tests/e2e/test-results/` (каталог в `.gitignore`), trace открывается командой `uv run playwright show-trace <trace.zip>` (в `tests/e2e`) или на trace.playwright.dev. С uv на машине тесты можно запустить и без Docker: `cd tests/e2e && uv run playwright install chromium && uv run pytest`.

### Линтер

Python-код четырёх сервисов (`app/`, `tests/`, `migrations/`) проверяет и форматирует [ruff](https://docs.astral.sh/ruff/) 0.17.2, настройки — [ruff.toml](ruff.toml) в корне: правила `E`, `F`, `W`, `I`, `B`, `UP`, длина строки 100. Версия одна для всех и задаётся в команде, в dev-группы сервисов ruff не добавлен. Запуск из корня репозитория:

```bash
uvx ruff@0.17.2 check .              # замечания линтера, код 0 — чисто
uvx ruff@0.17.2 format --check .     # код 0 — форматирование не нужно
uvx ruff@0.17.2 check --fix .        # исправить то, что ruff умеет сам
uvx ruff@0.17.2 format .             # отформатировать
```

Без uv на машине — тот же образ, что для тестов: `docker run --rm -v "$PWD":/repo -w /repo ghcr.io/astral-sh/uv:0.13.5-python3.14-trixie-slim uvx ruff@0.17.2 check --no-cache .` (`--no-cache` — чтобы не появлялся `.ruff_cache`).

Отключены `B008` (`Depends()` / `Query()` в значениях по умолчанию — обычный приём FastAPI) и `UP042` (`class X(str, Enum)` → `StrEnum` меняет `str()` у значений). В `tests/conftest.py` импорты приложения стоят после `os.environ[...] = …`: config и engine читают окружение при импорте. Порядок этих строк менять нельзя, а `E402` такие присваивания нарушением не считает. У `tests/e2e/` свой `[tool.ruff]` в `pyproject.toml`: правила из корневого `ruff.toml`, но `target-version = "py312"`. e2e работает на Python 3.12 из образа Playwright, а с py314 `ruff format` переписывает `except (A, B):` в синтаксис 3.14 без скобок.

Массовое переформатирование сделано отдельным коммитом, его хеш записан в [.git-blame-ignore-revs](.git-blame-ignore-revs). GitHub пропускает такие коммиты в blame сам, локально нужно один раз выполнить в своей копии репозитория:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Если файла нет (например, в старой ветке до шага 1.5.7), `git blame` с этой настройкой падает с ошибкой `could not open object name list`.

Shell-скрипты в `scripts/`, `tests/smoke.sh` и `tests/e2e/run.sh` проверяет [shellcheck](https://www.shellcheck.net/) v0.11.0 (в CI, замечаний 0): `docker run --rm -v "$PWD":/mnt:ro -w /mnt koalaman/shellcheck:v0.11.0 scripts/*.sh tests/smoke.sh tests/e2e/run.sh`.

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

Заполнение данных при смене схемы — в самой миграции (`op.execute`, SQL по диалекту, если SQLite и PostgreSQL расходятся, как в expand time-service), а не в коде сервиса: у запросов приложения лимит 5 с (`statement_timeout`), у миграций его нет. Ломающая смена схемы делится на expand и contract (см. [k8s/README.md](k8s/README.md#probes)): во время перекатки старые поды работают на новой схеме. Колонку удаляют только тогда, когда её не знает уже и предыдущая версия кода: ORM перечисляет в `SELECT` все колонки модели, и старый под на схеме без колонки отвечает 500. Поэтому сначала выкатывается код без колонки (пока колонка в базе, `alembic check` должен её пропускать — `include_object` в `migrations/env.py`), а удаляется она следующей миграцией, отдельной выкаткой; фильтр после этого убирают. Так в time удалены `minutes`, `date`, `is_active`: код без них — contract (`1a3e7ba4c4e7`), удаление — `30ac5e04a1c1`. На SQLite `DROP COLUMN` в batch пересоздаёт таблицу: CHECK и частичные индексы должны пережить это — проверяйте их тестом на head. Откат удаления возвращает колонку без старых данных. Долгое ожидание блокировки таблицы миграция обрывает сама (`SET LOCAL lock_timeout`, пример — contract и удаление колонок time).

Затем проверьте цикл `alembic upgrade head` → `alembic check` → `alembic downgrade base` → `alembic upgrade head`. Его выполняет `tests/test_migrations.py`: при расхождении моделей и миграций тест падает. Применить новую ревизию к базе стека: `docker compose up --build -d` (migrate-сервис выполнится сам) или `docker compose run --rm --no-deps ser-<service>-migrate alembic upgrade head`. Вне Docker те же команды запускаются в папке сервиса через uv: `uv run alembic upgrade head`, `uv run alembic check` и т. д.

### Kubernetes

Приложение запускается в локальном кластере [kind](https://kind.sigs.k8s.io/) (Kubernetes в Docker, один узел). Подробная инструкция — **[k8s/README.md](k8s/README.md)**: требования и версии, что делает каждый скрипт, устройство манифестов, диагностика (логи, Job, события), удаление кластера и известные ограничения. Нужны Docker (4 ГБ памяти), kind и kubectl.

```bash
brew install kind                # проверено на v0.33.0
./scripts/kind-up.sh             # кластер freelance + Envoy Gateway + сборка и загрузка образов ser-*:<SHA коммита>
./scripts/init-k8s-env.sh        # k8s/overlays/local/app.env и db.env со случайными секретами
./scripts/k8s-deploy.sh          # манифесты, миграции, тестовые пользователи, ожидание готовности
open http://127.0.0.1:8080       # приложение (вход admin@example.com / password123)
```

Кратко:
- манифесты собирает kustomize: [k8s/base](k8s/base) без локальных допущений, [k8s/overlays/local](k8s/overlays/local) для kind (Secret'ы из `app.env` и `db.env`, `imagePullPolicy: Never`, класс входа и политика `entry`: Envoy закрывает простаивающие соединения к бэкендам через 60 с, раньше uvicorn и nginx), [k8s/overlays/local-seed](k8s/overlays/local-seed) добавляет Job тестовых пользователей;
- вход один — Gateway API (Envoy Gateway v1.9.2) на `http://127.0.0.1:8080`: `/api` → `ser-gateway`, остальное → `ser-frontend`, все сервисы `ClusterIP`;
- миграции — Job `auth-migrate`, `task-migrate`, `time-migrate`, seed — Job `auth-seed`. Порядок задаёт `k8s-deploy.sh`. Деплоить только через него: Job неизменяемы, голый `kubectl apply -k` поверх старых Job падает или не перезапускает миграции;
- образы в кластере помечены SHA коммита (`<sha>-dirty-<время>` при незакоммиченных правках): после правок достаточно `kind-up.sh` и `k8s-deploy.sh`, поды перекатываются сами, без пересборки — не трогаются. `k8s-deploy.sh` отказывается выкатывать тег, собранный не из текущего дерева (другой коммит, правки после сборки), и просит запустить `kind-up.sh`; выкатить такой тег намеренно — `ALLOW_STALE_TAG=1`. Реестра нет, образы загружаются в узел (`imagePullPolicy: Never`), compose остаётся на `:latest`;
- по две реплики у auth, task, time, gateway и frontend, базы — по одной;
- Pod Security Admission `restricted` (не root, без привилегий, корень только на чтение), NetworkPolicy по умолчанию запрещают всё, кроме нужных связей;
- readiness сервисов — `/ready` (база и ревизия схемы), liveness — `GET /`: под без базы или до миграций снимается с трафика, но не перезапускается; лимита CPU у приложений нет (вход 0,25–0,3 с вместо ~2,5 с), лимиты памяти есть;
- сквозной прогон против кластера — `SMOKE_MODE=k8s bash tests/smoke.sh` (179 проверок).

Удалить кластер: `kind delete cluster --name freelance`.

### CI

GitHub Actions, workflow [.github/workflows/ci.yml](.github/workflows/ci.yml). Запускается на каждый push в любую ветку, на pull request и вручную (Actions → CI → Run workflow). Новый push в ту же ветку отменяет устаревший прогон (`concurrency`). У каждого job есть `timeout-minutes`, права токена — только `contents: read`. Jobs идут параллельно:

| Job | Что проверяет |
|---|---|
| `lint` | `ruff check` и `ruff format --check` (0.17.2), shellcheck (`scripts/*.sh`, `tests/smoke.sh`, `tests/e2e/run.sh`), [actionlint](https://github.com/rhysd/actionlint) по workflow (и shellcheck внутри `run:`), [gitleaks](https://github.com/gitleaks/gitleaks) по всей истории git (найденное печатается скрытым, `--redact`; стандартные правила плюс allowlist фиктивных JWT-ключей тестов в `.gitleaks.toml`) |
| `python` (×4: auth, task, time, gateway) | `uv sync --locked`, `uv run pytest --cov=app`: порог покрытия из `pyproject.toml`, тест миграций на PostgreSQL 15 (service container, `TEST_POSTGRES_URL`). Пропущенный тест роняет job: значит, база не подключилась |
| `frontend` | Node из `.nvmrc` (24), `npm ci`, `npm run typecheck`, `npm run build` |
| `static` | `docker compose config --quiet` на `.env` от `init-env.sh`, kubeconform v0.8.0 по выводу `kubectl kustomize` обоих overlay (как в [k8s/README.md](k8s/README.md#диагностика)) |
| `compose` | с чистого раннера: `init-env.sh` → `docker compose up --build -d --wait` → smoke (181) → e2e (`http://127.0.0.1:5173`), в конце `down -v` |
| `kind` | `kind-up.sh` → `init-k8s-env.sh` → `k8s-deploy.sh` → smoke k8s (179) → e2e через вход (`http://127.0.0.1:8080`) → `kubectl apply --dry-run=server` обоих overlay с развёрнутым тегом (`k8s/overlays/.deploy/app` и `seed`) |

Где смотреть: вкладка **Actions** репозитория, workflow **CI**, бейдж в начале README показывает статус последнего прогона. Если падают compose или kind, отдельный шаг «диагностика» печатает состояние: для compose — `docker compose ps -a` и последние строки логов, для kind — поды и Job, Deployment с тегами образов, события, `describe gateway entry`, логи подов (и прошлых контейнеров) и контроллера Envoy Gateway. Скриншоты и trace упавших e2e-тестов приходят артефактом прогона (`e2e-compose`, `e2e-kind`, хранятся 7 дней). Повторить job локально можно теми же командами, что в разделах «Тесты», «Линтер» и в [k8s/README.md](k8s/README.md).

Прогон целиком занимает около 4,5 минуты: дольше всех идёт `kind` (~4 мин: `kind-up.sh` ~1,5 мин, деплой ~1 мин, smoke и e2e ~1,5 мин), `compose` ~2 мин, остальные jobs укладываются в 10–40 с. Лимит `timeout-minutes` — 5 минут у лёгких jobs, 10 у `compose`, 15 у `kind`.

Секреты в CI не хранятся: `init-env.sh` и `init-k8s-env.sh` генерируют их заново в каждом прогоне. Сразу после этого workflow регистрирует значения (для k8s — и их base64) через `::add-mask::`, и если значение где-то всплывёт, GitHub заменит его в логе на `***`. Маскирование — только страховка: `docker compose config` запускается только с `--quiet` (без него печатает пароли), вывод `kubectl kustomize` (Secret'ы в base64) идёт только в pipe, `set -x` в workflow и скриптах не включать.

Версии закреплены так же, как локально:
- actions — полным SHA коммита с версией в комментарии (`actions/checkout@3d3c42e… # v7.0.1`): тег можно перевесить на другой код, SHA — нет. При обновлении берётся SHA из тега релиза, комментарий меняется вместе с ним. actionlint не проверяет входы actions, закреплённых по SHA, поэтому входы сверяются с `action.yml` этой версии вручную;
- инструменты — образы по digest (shellcheck, actionlint, gitleaks, kubeconform) и бинарники с проверкой sha256: uv 0.13.5 (`checksum` у setup-uv), kubectl v1.35.9 (на раннере kubectl 1.37, а сервер kind — 1.35, это больше допустимой разницы в одну минорную версию). У kind проверяется версия на раннере (v0.33.0): если образ раннера её поменяет, job упадёт с понятной ошибкой;
- PostgreSQL в job `python` — `postgres:15-alpine`, тот же тег, что в compose и манифестах.

Обновления зависимостей предлагает Dependabot ([.github/dependabot.yml](.github/dependabot.yml)) раз в неделю (понедельник): uv (четыре сервиса — одной группой), npm (фронтенд), GitHub Actions (SHA и комментарий с версией обновляются вместе), Docker (`FROM` в Dockerfile, тег и digest). Патчи и минорные приходят одним PR на экосистему, мажорные — отдельными PR. e2e (`tests/e2e/uv.lock` и образ Playwright) — один общий PR (`multi-ecosystem-groups`): пакет `playwright` и образ должны быть одного релиза. Не предлагаются минорные и мажорные версии образа `python` и мажорные `node`: они меняются вместе с `requires-python`, `.nvmrc` и CI. PR вливаются вручную после зелёного CI.

Часть версий Dependabot не видит, поэтому PR бота сверяется вручную:
- **образ uv** (`ghcr.io/astral-sh/uv:<версия>@sha256:…`): в Dockerfile сервисов его обновляет PR docker, в `tests/e2e/Dockerfile` — общий PR e2e, версии в них должны совпадать. Та же версия должна быть в `ci.yml` — `UV_VERSION` и `UV_CHECKSUM` (sha256 архива `uv-x86_64-unknown-linux-gnu.tar.gz` из релиза uv, рядом лежит файл `.sha256`), и в рецептах этого README (`ghcr.io/astral-sh/uv:<версия>-python3.14-trixie-slim` в «Тестах» и «Линтере», «проверено на» в «Локальном запуске», версия uv в «e2e в браузере»). Правка — коммитом в ветку PR до вливания, иначе CI и Docker разойдутся по версии uv;
- **мажорные npm** (vite, vue-router, pinia, `@vitejs/plugin-vue`, TypeScript) не вливаются до фазы 3 (ROADMAP). Закрытый PR бот не повторяет до следующей версии;
- **Python-пакеты** приходят одним PR на четыре `uv.lock`; версии FastAPI и SQLAlchemy упомянуты в «Стеке» и «Текущем состоянии» — поправить там при минорном обновлении;
- **actions**: SHA и комментарий с версией меняются вместе, входы новой версии сверяются с её `action.yml` (actionlint их не проверяет).

Совсем вне Dependabot (раз в этап сверять с последними релизами): образы shellcheck, actionlint, gitleaks, kubeconform (digest) и версии kubectl, kind, ruff в `ci.yml` (`env`; ruff — ещё в «Линтере»), Envoy Gateway (`kind-up.sh`, sha256 `install.yaml`) и узел kind (`k8s/kind-config.yaml`), `postgres:15-alpine` в compose, манифестах, job `python` и рецептах README (мажорная версия базы требует переноса данных).

## Конфигурация

Основные переменные окружения. Для Docker Compose общие переменные (`SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, пароли баз, `BIND_ADDR`, `CORS_ORIGINS`, `SEED_TEST_USERS`) задаются в корневом `.env`: шаблон — [.env.example](.env.example), создаёт файл `./scripts/init-env.sh`, в git `.env` не попадает. Остальное (адреса сервисов, `GATEWAY_URL` фронтенда, `DATABASE_URL`, который собирается из паролей в `.env`) задано в `docker-compose.yml`. В Kubernetes `SECRET_KEY` берётся из `k8s/overlays/local/app.env` (Secret `app-secrets`), пароли баз — из `db.env` (Secret `db-credentials`), `DATABASE_URL` собирается в манифесте подстановкой `$(DB_PASSWORD)`, а несекретное (`ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, адреса сервисов) лежит в ConfigMap `service-config`. Для запуска без Docker все переменные с описанием собраны в файлах `.env.example` в папке каждого сервиса и в `frontend/login_page`.

| Переменная | Где используется | Описание |
|------------|------------------|----------|
| `DATABASE_URL` | auth, task, time | Строка подключения SQLAlchemy, например `postgresql+psycopg://user:password@host:5432/db` или `sqlite:///./auth.db`. Обязательна: без неё сервис не стартует |
| `SECRET_KEY` | все сервисы | Ключ подписи JWT, должен быть одинаковым везде. Обязателен: без него сервисы не стартуют |
| `ALGORITHM` | все сервисы | Алгоритм подписи, по умолчанию `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | auth | Время жизни access-токена |
| `LOGIN_MAX_ATTEMPTS` | auth | Сколько входов на один email допускается за окно; по умолчанию `5`. Следующие попытки до конца окна — `429` без проверки пароля |
| `LOGIN_WINDOW_SECONDS` | auth | Окно счётчика входов в секундах от первой попытки; по умолчанию `900` (15 минут) |
| `AUTH_DB_PASSWORD`, `TASK_DB_PASSWORD`, `TIME_DB_PASSWORD` | compose (БД и `DATABASE_URL`) | Пароли баз. Обязательны, генерирует `init-env.sh` |
| `SEED_TEST_USERS` | auth (`python -m app.init_users`) | `true` — команда seed создаёт тестовых пользователей, иначе пропускает их создание. Только для разработки. По умолчанию `false`; в compose задаётся только у `ser-auth-seed`: из `.env` (`true` в шаблоне) или из окружения, дефолт тоже `true` |
| `AUTH_URL`, `TASK_URL`, `TIME_URL` | gateway | Адреса внутренних сервисов |
| `BIND_ADDR` | compose (`ports` у frontend и gateway) | Адрес хоста, на котором публикуются 5173 и 8000. По умолчанию `127.0.0.1` (только эта машина), `0.0.0.0` — все интерфейсы |
| `CORS_ORIGINS` | gateway | Адреса фронтенда, которым разрешены запросы из браузера, через запятую. По умолчанию `http://localhost:5173,http://127.0.0.1:5173`. В Kubernetes — ключ `cors-origins` ConfigMap `service-config`: `http://localhost:8080,http://127.0.0.1:8080` (адрес входа; браузер ходит на один origin, значение нужно для явности и проверки preflight). Внутренние сервисы CORS не настраивают: браузер обращается только к gateway |
| `TIME_SERVICE_URL` | task | Адрес Time Service для сбора статистики |
| `TASK_SERVICE_URL` | time | Адрес Task Service: при старте таймера, ручной записи и смене задачи в записи time-service проверяет задачу. По умолчанию `http://127.0.0.1:8002`, в compose — `http://ser-task:8002`, в Kubernetes — ключ `task-url` ConfigMap `service-config` |
| `GATEWAY_URL` | frontend (nginx, при запуске контейнера) | Адрес gateway без пути, куда nginx проксирует `/api/`. В compose — `http://ser-gateway:8000`. Имя резолвится при запросах (DNS Docker), поэтому пересоздание gateway не требует перезапуска фронтенда. В Kubernetes — ключ `gateway-url` ConfigMap `service-config`, значение `http://ser-gateway.freelance-service.svc.cluster.local:8000` (полное имя): `resolver` nginx не применяет search-домены из `/etc/resolv.conf`, и короткое `ser-gateway` даёт 502 (`could not be resolved`) |
| `VITE_API_BASE` | frontend (на этапе сборки) | Необязательна. Пусто или не задана — запросы идут на тот же адрес по пути `/api` (в Docker их проксирует nginx, в `npm run dev` — Vite). В образе не задаётся, один образ годится для любого окружения |

`SECRET_KEY` и пароли баз (`AUTH_DB_PASSWORD`, `TASK_DB_PASSWORD`, `TIME_DB_PASSWORD`) в compose обязательны и берутся из `.env`; их генерирует `init-env.sh`. Пароль подставляется в `DATABASE_URL`, поэтому только символы `[A-Za-z0-9_-]` (`@`, `:`, `/` ломают URL). Пароль применяется при создании тома БД: если вы обновились с версии, где пароли были зашиты в compose, один раз выполните `docker compose down -v` (данные при этом удаляются).

## API

Все запросы идут через gateway с префиксом `/api`. Все эндпоинты, кроме `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh` и служебных `/health`, `/ready` и `/` у gateway, требуют заголовок `Authorization: Bearer <access-токен>`.

У проектов и задач в ответах есть `owner_id` — id владельца. Его задаёт сервер: при создании берётся из токена, у задачи в проекте — владелец проекта; поле `owner_id` в теле запроса игнорируется.

Проекты и задачи «только свои»: пользователь в списках видит только свои (фильтры работают внутри своих, `total` считается тоже по своим), чужой проект или задача для него — `404`, как несуществующие. admin видит и меняет всё. Создать задачу можно только в своём проекте (admin — в любом, задача получает владельца проекта); перенести задачу через `PATCH` с `project_id` — только в проект её владельца (user в чужой — `404`, admin — `400`); несуществующий проект, в том числе `project_id=0`, — `404`.

Правка проекта и задачи — `PATCH` с семантикой merge-patch: нет поля в теле — поле не меняется; `null` очищает `description`, `deadline` и `project_id` задачи (вынос из проекта) и `description` проекта; `null` у `title`, `status`, `is_active` задачи и `name`, `is_active` проекта, неизвестное поле (опечатка, `owner_id`) или неверное значение — `422`; пустое тело — `200` без изменений (`updated_at` задачи меняется только при реальной правке). Название задачи и проекта в `POST` и `PATCH` — от 1 до 255 символов после обрезки пробелов по краям (иначе `422`); `deadline` — только с часовым поясом (`…Z` или смещение), без пояса — `422`. `PUT` у задач и проектов нет — `405`.

Коды ошибок: без токена, с неверным, просроченным или refresh-токеном вместо access — `401`; не хватает прав (например, не admin) — `403`; неизвестный путь — `404`. Заголовки `X-User-*` от клиента игнорируются.

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/register` | Регистрация. Email без учёта регистра: хранится в нижнем регистре, `User1@Example.COM` и `user1@example.com` — один адрес (повтор — 400) |
| POST | `/api/auth/login` | Вход, возвращает access и refresh токены. Email без учёта регистра. Каждая попытка считается по email до проверки пароля, в том числе для незарегистрированного адреса: шестая и следующие в окне 15 минут от первой — `429` «Too many login attempts» с заголовком `Retry-After` (секунды до конца окна), пароль при этом не проверяется, даже верный. Верный пароль до замка обнуляет счётчик (у отключённого пользователя тоже, ответ — `403`). `refresh` и `register` не считаются. Числа — `LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS` |
| POST | `/api/auth/refresh` | Обновление access-токена |
| GET | `/api/auth/me` | Текущий пользователь (`id`, `email`, `full_name`, `role`, `is_active`, `created_at`) |
| GET | `/api/auth/users` | Список пользователей, только admin (роль берётся из базы, не из токена; не admin — `403` «Admin role required»). Ответ — `{items, total, limit, offset}`; `limit` 1–200 (50), `offset` ≥ 0, `sort` — `created_at`, `-created_at` (по умолчанию), `email`, `-email`, при равенстве по `id`. Фильтры: `role` (`user`/`admin`), `is_active`, `q` — подстрока в email или имени без учёта регистра (1–100 символов, `%`, `_` и `\` — обычные символы), `id` — повторяемый, до 200 значений. Неверное значение или лишний `id` — `422`; `total` считается с теми же фильтрами; отключённые пользователи тоже в списке. Кириллица в другом регистре находится только на PostgreSQL |
| PATCH | `/api/auth/users/{id}` | Смена роли и отключение, только admin (по базе). Тело `{role?, is_active?}`: нет поля — не меняется, `null`, неизвестное поле или неверное значение — `422`, пустое тело — `200` без изменений. Себя менять нельзя — `409` «Cannot change your own role or status»; нет пользователя — `404`; тот, кто делает запрос, к этому моменту уже не активный admin — `403`. Ответ — пользователь, как в списке. Удаления нет (`DELETE` — `405`), только отключение: отключённый сразу не может войти (`403`), обновить токен и получить `/me` (`401`), его данные остаются. Каждое изменённое поле пишется в журнал `user_audit` (в базе auth, API нет) |
| GET, POST | `/api/tasks/projects` | Свои проекты (admin — все) и создание проекта. Список — конверт `{items, total, limit, offset}`: `limit` 1–200 (50), `offset` ≥ 0, `sort` — `created_at`, `name` с `-` и без (по умолчанию `-created_at`, новые сверху; `name` без учёта регистра по `lower`, кириллица в другом регистре — только на PostgreSQL; при равенстве по `id` в ту же сторону), фильтр `is_active` (без него — все); `total` — с теми же фильтрами, неверное значение — `422`. Каждый проект списка дополнен `tasks_count` (число активных задач проекта) и `tasks_preview` (первые 3 активные задачи по `created_at`, `id`: `{id, title, status}`; архивные не считаются, проект без задач — `0` и `[]`); счётчик и превью — два дополнительных SQL-запроса на страницу при любом числе проектов, у admin счётчики чужих проектов те же. В `GET /projects/{id}` и во вложенном `project` у задачи этих полей нет |
| GET, PATCH, DELETE | `/api/tasks/projects/{id}` | Проект: свой, у admin — любой, чужой — `404`. `PATCH` — `{name?, description?, is_active?}` (правила — под таблицей); без `is_active` архив не снимается. `DELETE` удаляет и задачи проекта |
| GET, POST | `/api/tasks/tasks` | Свои задачи (admin — все) и создание задачи. Список — конверт, как у проектов (`limit`, `offset`, `total`); `sort` — `created_at`, `updated_at`, `deadline`, `title`, `status` с `-` и без (по умолчанию `-created_at`): `NULL` всегда в конце, `updated_at` у задачи без правок — время создания, `title` по `lower` (кириллица в другом регистре — только на PostgreSQL), `status` — в порядке `todo`, `in_progress`, `done`, `blocked`, при равенстве по `id`. Фильтры: `project_id` — число или `none` (задачи без проекта), `status` — повторяемый (`?status=todo&status=done`), `is_active`. Неверное значение — `422`. У каждой задачи вложенный `project` |
| GET, PATCH, DELETE | `/api/tasks/tasks/{id}` | Задача: своя, у admin — любая, чужая — `404`. `PATCH` — `{title?, description?, status?, deadline?, project_id?, is_active?}` (правила — под таблицей); `project_id: null` выносит задачу из проекта, владелец прежний |
| POST | `/api/tasks/tasks/{id}/status` | Смена статуса задачи |
| GET | `/api/tasks/statistics/users` | Статистика по пользователям (только admin): task запрашивает её у time-service с токеном пользователя и отдаёт ответ как есть; time недоступен или ответил ошибкой — `502` |
| GET | `/api/time/time-entries` | Список записей, конверт `{items, total, limit, offset}`. Пользователь видит только свои, admin — все (фильтр `user_id`; чужой `user_id` у пользователя — `403`). Фильтры: `task_id`, `from`/`to` по `started_at` (время с поясом; `from` включительно, `to` не включительно). `limit` по умолчанию 50, от 1 до 200, `offset` ≥ 0, `sort` — `-started_at` (по умолчанию) или `started_at`, при равенстве по `id`; лишнее — `422` |
| POST | `/api/time/time-entries` | Ручная запись `{task_id, started_at, stopped_at, description?}` (время с поясом) → `201`; `user_id` берётся из токена, `duration_seconds` считает сервер. `stopped_at` раньше `started_at` или `started_at`/`stopped_at` позже «сейчас» + 1 минута — `422`. Задачу проверяет task-service так же, как при старте таймера (`404`, `409`, `503`, `502`) |
| PATCH | `/api/time/time-entries/{id}` | Правка своей записи (admin — любой, чужая — `404`): `description` (`null` очищает), `started_at`, `stopped_at`, `task_id`; нет поля в теле — не меняется, `null` у остальных и неизвестное поле (опечатка, `user_id`) — `422`. `duration_seconds` пересчитывает сервер; `stopped_at` у идущей записи не ставится (`422`), задача проверяется, только если `task_id` есть в теле |
| DELETE | `/api/time/time-entries/{id}` | Удаляет свою запись (admin — любую, чужая — `404`), `204`; идущую тоже — таймер при этом останавливается |
| GET | `/api/time/timer` | Свой идущий таймер: `{"entry": запись или null, "server_time"}` |
| POST | `/api/time/timer/start` | `{task_id, description?}` → `{"entry", "stopped", "server_time"}`: новая запись — `201`, идущая на другой задаче закрывается (`stopped`); та же задача уже идёт — `200` с ней; параллельный старт не удался и после повтора — `409`. Задачу проверяет task-service с токеном пользователя: чужая или несуществующая — `404` «Task not found», задача или её проект в архиве (`is_active=false`) — `409` «Task is archived» (в том числе та же идущая), task недоступен (таймаут, сеть, 5xx) — `503` «Task service unavailable», task отклонил токен — `502` |
| POST | `/api/time/timer/stop` | → `{"stopped": закрытая запись или null, "server_time"}`, всегда `200` |
| GET | `/api/time/statistics/users` | Статистика времени по пользователям (только admin): `user_id`, `entries_count`, `tasks_count` (разные задачи), `total_seconds`, `avg_seconds_per_task`; считаются закрытые записи, идущий таймер не входит. Email и имя в ответе нет: их подставит фронтенд по `user_id` |

Таймер у каждого пользователя свой, один на пользователя (admin — тоже только свой); идущий таймер — запись без `stopped_at`. Запись времени: `id`, `user_id`, `task_id`, `started_at`, `stopped_at`, `duration_seconds` (целые секунды, считает сервер при остановке; запись любой длины сохраняется), `description`, `created_at`, `updated_at`. Время в ответах — UTC с поясом (`…Z`), «сейчас» — часы сервиса. Стоп и `GET /timer` в task-service не ходят и работают, даже когда он недоступен; идущий таймер на задаче, ушедшей в архив, не останавливается.

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
│   └── e2e/             e2e в браузере (pytest-playwright): авто-refresh, «только свои», счётчик задач, роут `/`, таймер, страница пользователей, email в статистике и роль после смены, архив, страницы и сортировка, окна правки; run.sh — запуск в Docker
├── scripts/             вспомогательные скрипты (init-env.sh — .env, init-k8s-env.sh — секреты кластера, kind-up.sh — кластер kind и образы, k8s-deploy.sh — деплой в кластер)
├── .github/             CI (GitHub Actions): workflows/ci.yml; dependabot.yml — еженедельные обновления зависимостей
├── .env.example         шаблон общих переменных для Docker Compose
├── .git-blame-ignore-revs коммиты форматирования, которые пропускает git blame
├── .gitleaks.toml       allowlist gitleaks: фиктивные JWT-ключи тестов
├── ruff.toml            настройки линтера и форматтера Python (ruff)
└── docker-compose.yml
```

## Текущее состояние

Проект работает как рабочий прототип, но не готов к продакшену. Что уже сделано и какие ограничения предстоит закрыть:

- Gateway проверяет Bearer access-токен (подпись, срок `exp`, тип `access`) для всех путей, кроме `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/health`, `/ready` и `/`. Без токена или с неверным токеном ответ 401, неизвестные пути 404. Клиентские заголовки `X-User-*` затираются, gateway ставит свои `X-User-Id` и `X-User-Role` из токена
- task-service и time-service сами проверяют access-токен так же, как gateway (подпись, `exp`, тип `access`), и не доверяют заголовкам `X-User-*`: без токена 401, в том числе при обращении в обход gateway. Статистика по пользователям только для admin; task-service при сборе статистики передаёт в time-service токен пользователя. В time-service `user_id` записи берётся только из токена (поле `user_id` в теле игнорируется), пользователь видит только свои записи, admin — все
- У проектов и задач есть владелец (`owner_id`, NOT NULL): при создании он берётся из токена, задача в проекте получает владельца проекта. Проекты создают все пользователи. Пользователь видит, меняет и удаляет только свои проекты и задачи (на чужие — 404), admin — все; задача не может оказаться в проекте другого владельца. Старт таймера time-service проверяет у task-service (`GET /api/tasks/tasks/{id}` с токеном пользователя): чужая задача — 404, архивная — 409, task недоступен — 503; так же проверяются ручная запись и смена задачи в записи
- auth-service: роль в access-токене берётся из БД и при входе, и при обновлении токена; отключённый (`is_active=false`) или удалённый пользователь не может войти, обновить токен и получить `/api/auth/me`. Вход с неизвестным email тоже проверяет пароль (против заранее вычисленного фиктивного хеша bcrypt), поэтому по времени ответа не видно, зарегистрирован ли email. Хеши паролей — bcrypt `$2b$12$`, хеши, созданные прежней библиотекой passlib, проверяются без перехеширования. Email хранится в нижнем регистре: `register` и `login` приводят весь адрес (`EmailStr` сам приводит только домен), поэтому `User1@…` и `user1@…` — один аккаунт и войти можно в любом регистре; адреса, сохранённые раньше, привела миграция `37998bcc3290` (если бы нашлись адреса, совпадающие без учёта регистра, она остановилась бы со списком, ничего не меняя). `GET /api/auth/users` — список для admin: admin определяется по роли в базе (`crud.get_current_admin`), поэтому снятый admin теряет доступ сразу, а не через срок жизни токена; фильтры `role`, `is_active`, `q`, `id`, сортировка по `created_at` и `email` (по `role` нет: PostgreSQL сортирует enum в порядке объявления, SQLite — по алфавиту), `created_at` теперь есть и в `/me` и в ответе `register`. `PATCH /api/auth/users/{id}` — смена роли и отключение (admin, по базе): одна транзакция блокирует строки всех активных admin (`SELECT … FOR UPDATE` по `id`) и проверяет, что тот, кто делает запрос, всё ещё среди них, а менять себя нельзя, поэтому хотя бы один активный admin остаётся всегда, в том числе когда два admin одновременно понижают друг друга (второй получает 403 — тест на PostgreSQL). Каждое изменённое поле — строка в таблице `user_audit` (кто, кого, поле, было, стало, когда) в той же транзакции; читается через `psql`. Неудачные входы считаются по email в таблице `login_attempts`: попытка засчитывается до проверки пароля одним `INSERT … ON CONFLICT … RETURNING` (номер попытки атомарен и при параллельных запросах через обе реплики — тест на PostgreSQL: из 8 одновременных bcrypt проверяет ровно 5 паролей), с шестой в окне 15 минут — 429 с `Retry-After`; успешный вход удаляет свою строку и строки с истёкшим окном. Ключ `SECRET_KEY` обязателен. Тестовых пользователей сервис при старте не создаёт: это делает отдельная команда `python -m app.init_users` (в compose — контейнер `ser-auth-seed`) и только при `SEED_TEST_USERS=true`, вывод идёт через logging и виден в `docker logs ser-auth-seed`; в локальном кластере то же делает Job `auth-seed` (`k8s/overlays/local-seed`, в base его нет)
- Python-сервисы в образах работают не от root (пользователь `app`, в Dockerfile `USER 10001` числом — так его проверяет Kubernetes), код в образе доступен только на чтение. В `/app` образа попадают только `app/`, а у auth, task и time ещё `migrations/` и `alembic.ini` (миграции в compose и Job в Kubernetes запускаются на том же образе); тесты, README, `.env.example`, `Dockerfile`, `pyproject.toml` и `uv.lock` в образ не копируются (по `pyproject.toml` и `uv.lock` ставятся зависимости на этапе сборки)
- В Kubernetes на namespace приложения включён Pod Security Admission `restricted`: все поды (сервисы, Job, базы) работают не от root (10001 / 101 / 70), без повышения привилегий и capabilities, с seccomp `RuntimeDefault`, корневой файловой системой только на чтение (nginx и postgres пишут в `emptyDir`) и без токена ServiceAccount. Под с нарушением API-сервер не создаёт
- У auth, task и time есть `GET /ready` (вне `/api`, через gateway недоступен): `SELECT 1` и ревизия схемы — таблицы `alembic_version` нет, она пустая или ревизия старше head миграций образа → 503, равна head или незнакома (новее: expand/contract) → 200, база недоступна → 503. Соединение к PostgreSQL (`connect_args` в `app/db.py`): новое — с таймаутом 2 с; запрос дольше 5 с отменяет сама база (`statement_timeout`); обрыв сети на открытом соединении ловят TCP keepalive (5 с простоя, затем пробы раз в 2 с, 3 пробы) и `tcp_user_timeout` 5 с — ошибка за 5–7 с вместо зависания; пул проверяет соединение перед выдачей (`pool_pre_ping`), поэтому после перезапуска базы первый запрос — 200, а не 500. Миграции идут через свой движок без этих настроек и через 5 с не обрываются. У gateway `/ready` всегда 200 (без проверки сервисов, их доступность — в `/health`). В Docker Compose healthcheck auth, task, time и gateway — `GET /ready`, у frontend — `GET /` nginx, у баз — `pg_isready` по своей базе; порядок старта задан через `depends_on: service_healthy`: task ждёт time, gateway — три сервиса, frontend — gateway, поэтому `up --wait` ждёт сервисы с базой и схемой. time не ждёт task (обратная зависимость замкнула бы цикл) и в `/ready` его не проверяет: пока task недоступен, старт таймера отвечает 503, остальное в time работает
- `.dockerignore` исключает `.env`, `*.db`, `.venv`, `node_modules` во всех папках, локальные настройки и базы больше не попадают в образы
- `SECRET_KEY` обязателен во всех сервисах, `DATABASE_URL` обязателен в auth, task и time: значений по умолчанию (в том числе SQLite-файла) нет, без них сервис не стартует. CORS настроен только в gateway и разрешает лишь адреса из `CORS_ORIGINS`
- Фронтенд сам обновляет access-токен: на ответ 401 он один раз запрашивает `/api/auth/refresh` (параллельные запросы ждут один общий refresh) и повторяет запрос. Если refresh не удался, токены удаляются и открывается страница входа. Оба сценария проверяет e2e-тест в браузере (`tests/e2e/`, compose и kind). Refresh-токен живёт 7 дней и не обновляется, после этого нужно войти заново
- Страница пользователей `/users` (только admin): роут с проверкой роли — при прямом переходе guard ждёт ответ `/api/auth/me`, не admin уходит на `/dashboard`; кнопка «Пользователи» в шапке дашборда есть только у admin. Таблица (email, имя, роль, активен, дата регистрации) берёт данные из `GET /api/auth/users`: фильтры по роли и статусу, поиск `q` с задержкой ввода 300 мс, страницы по 20 (`limit`/`offset`/`total`; фильтры сбрасывают страницу на первую). Действия «Сделать admin / user» и «Отключить / Включить» шлют `PATCH`, строка обновляется из ответа; у своей строки действий нет. Ошибки 403, 409 и 422 показываются тостом с `detail` сервера. Вид страницы — фаза 3. Проверяют два e2e-теста (`tests/e2e/test_users.py`).
- Статистика admin показывает email и имя пользователей: после `GET /api/tasks/statistics/users` дашборд собирает `user_id` и запрашивает `GET /api/auth/users?id=1&id=2…` порциями по 200 (фронт повторяет параметр, а не шлёт `id[]=`). Нет пользователя или auth ответил ошибкой — в строке остаётся «#id», таблица видна, ошибка уходит в консоль без тоста. Роль после смены при открытой сессии: сразу после `/me` стор сравнивает `role` с claim `role` в теле access-токена (подпись не проверяет, её проверяет сервер); не совпали — один общий refresh (тот же, что на 401) и один повторный `/me`, без цикла. Повышенный до admin видит «Статистику» и получает её без повторного входа после перезагрузки страницы, а не через 15 минут. Проверяют два e2e-теста (`tests/e2e/test_statistics.py`)
- Кнопка «Выполнено» в списке задач проекта ставит статус `done`, а не удаляет задачу. Выполненные задачи показываются отдельным сворачиваемым блоком под текущими
- Python 3.14 во всех образах. В Docker Compose и Kubernetes сервисы работают с PostgreSQL через psycopg 3 (`postgresql+psycopg://`). Зависимости бэкенда ведёт uv: прямые закреплены точными версиями (`==`) в `pyproject.toml` сервиса, все вместе с транзитивными — в `uv.lock` (версии и хеши), общие пакеты одинаковы во всех сервисах (FastAPI 0.160.0, SQLAlchemy 2.1.6, pydantic-settings 2.16.1; httpx 0.28.1 — в task, time и gateway). Модели auth, task и time описаны через `Mapped[]`/`mapped_column`, nullability колонок совпадает с миграциями (тест `alembic check`). Обновления версий предлагает Dependabot (см. «CI»). Образ ставит их `uv sync --locked` (сборка падает, если `uv.lock` не совпадает с `pyproject.toml`) в `/opt/venv`; сам uv в итоговый образ не попадает. `pytest`, `httpx2` и `pytest-cov` — в dev-группе, в образ не ставятся
- Схема БД auth-service, task-service и time-service управляется миграциями Alembic (`<service>/migrations/`): в Docker Compose их применяют сервисы `ser-auth-migrate`, `ser-task-migrate` и `ser-time-migrate` до старта своего сервиса, в Kubernetes — Job `auth-migrate`, `task-migrate`, `time-migrate` (один раз на деплой, порядок задаёт `scripts/k8s-deploy.sh`). Тест в каждом из них проверяет, что миграции совпадают с моделями
- Проекты хранятся только в task-service: дубль проектов в time-service (`/api/time/projects`) удалён, фронтенд создаёт проект одним запросом. `user_id` записи времени обязателен (NOT NULL), фронтенд его не отправляет: сервер берёт `user_id` из токена
- В time-service есть серверный таймер (`/api/time/timer`, `start`, `stop`): запись хранит `started_at`, `stopped_at` и `duration_seconds`, у пользователя один идущий таймер — это гарантирует частичный уникальный индекс в базе, старт на другой задаче останавливает идущий в той же транзакции, параллельный старт с другой реплики повторяется один раз; перед стартом, ручной записью и сменой задачи в записи задача проверяется у task-service (один HTTP-клиент на процесс, таймауты 2 с на соединение и 3 с на ответ). Записи можно добавлять вручную, править и удалять через API (`POST`, `PATCH`, `DELETE /api/time/time-entries`), список постраничный; интерфейса для этого пока нет. Статистику task берёт у time одним клиентом на процесс (таймауты 2 с на соединение и 7 с на ответ: запрос к базе обрывается через 5 с). В таблице статистики админа — пользователь (email и имя из auth, см. ниже), записи, задачи, всего и среднее на задачу в `чч:мм`. Фронтенд работает на серверном таймере: состояние хранит store (Pinia) и перечитывает его при открытии дашборда, при возврате на вкладку (`visibilitychange`), при открытии окна таймера и после своих действий; секунды считает в браузере от `started_at` с поправкой часов по `server_time`, без опроса сервера. «Пауза» — стоп, «Продолжить» — старт той же задачи; заметка уходит со стартом (`description`), её можно менять и во время работы, и после паузы — окно через 0,6 с после ввода шлёт `PATCH` записи, а при паузе и закрытии окна дописывает несохранённое. Ошибки старта показываются тостом по смыслу (задача не найдена, в архиве, сервис задач недоступен), после ошибки состояние перечитывается; ошибка смены статуса на «В работе» таймер не останавливает. Схема переходит на новые поля по схеме expand/contract. Expand добавил новые колонки рядом со старыми. Contract дозаполнил записи окна expand и поставил `started_at NOT NULL`, CHECK и индекс «один идущий таймер» по `stopped_at IS NULL`. Старые колонки (`minutes`, `date`, `is_active`) удалены третьей выкаткой — после кода, который их уже не знает. Все три перекатки под нагрузкой прошли без ошибок от схемы (подробно — [k8s/README.md](k8s/README.md#probes))
- Автотесты (pytest) есть у всех бэкенд-сервисов (с PostgreSQL: gateway 81, auth 145, task 171, time 164; без `TEST_POSTGRES_URL` тесты миграций, `/ready`, таймаутов к базе и гонок таймера, смены роли и счётчика входов на PostgreSQL пропускаются — 81 / 127 + 18 skipped / 149 + 22 skipped / 139 + 25 skipped), покрытие 100 / 97,2 / 100 / 99,7 % с порогом в `pyproject.toml`. Python-код проверяет ruff (`ruff.toml`, см. «Линтер»), типы фронтенда — `npm run typecheck` (vue-tsc, 0 ошибок). Сквозные проверки: smoke (`tests/smoke.sh`, compose 181, k8s 179) и e2e в браузере (`tests/e2e/`, 23 теста: авто-refresh, неудачный refresh, «только свои», счётчик задач, роут `/`, таймер после перезагрузки, короткая запись, стоп без `done`, время задачи А не пишется в Б, `/users` закрыта для user, admin отключает и включает пользователя, admin видит email user1 в статистике, повышенный пользователь получает статистику после перезагрузки без повторного входа, проект и задача уходят в архив и возвращаются, страницы и сортировка панели проекта, окна правки задачи и проекта, задачи вне проекта). Всё это, а также shellcheck, gitleaks, kubeconform и сквозные прогоны в compose и kind с нуля, выполняет CI (GitHub Actions) на каждый push и pull request (см. «CI»)
- Фронтенд в Docker собирается multi-stage на Node 24 (`npm ci`, `vite build`) и раздаётся nginx без root (`nginx-unprivileged`, слушает 8080): долгий кэш для `/assets/`, `index.html` без кэша, gzip, SPA-роуты отдают `index.html`. Запросы `/api/` nginx проксирует на gateway, поэтому браузер ходит на один адрес и CORS для фронтенда не нужен. В Kubernetes фронтенд описан под этот образ: порт 8080, `GATEWAY_URL` из ConfigMap, startup/liveness/readiness `GET /`, Service `ClusterIP`
- В Kubernetes вход один — Gateway API (Envoy Gateway v1.9.2) на `http://127.0.0.1:8080`: `/api` → gateway, остальное → фронтенд; `LoadBalancer` и `NodePort` в namespace приложения нет, все сервисы `ClusterIP`. Автомасштабирования нет: у stateless-сервисов (auth, task, time, gateway, frontend) по две реплики, базы — по одной. Остановка подов плавная: `preStop` 5 с (Envoy и kube-proxy успевают убрать под из балансировки), затем uvicorn до 20 с дообрабатывает начатые запросы (`--timeout-graceful-shutdown` в образе; nginx фронта получает `SIGQUIT`), `terminationGracePeriodSeconds` 30; простаивающее keep-alive соединение закрывает клиент (Envoy — 60 с, httpx — 5 с), а uvicorn держит 75 с, поэтому 503 от Envoy на простоявшем соединении больше нет (см. «Архитектура»); перекатка под непрерывной нагрузкой проходит без ошибок у идемпотентных запросов (до этого — 502/503/504 у всех пяти Deployment), у POST и PATCH — редкие исключения (см. ограничения ниже). Кластер — только локальный kind (`./scripts/kind-up.sh`, ставит и Envoy Gateway, собирает и загружает образы с тегом по SHA коммита, убирает из узла старые), манифесты собираются kustomize (`base` + `overlays/local`), деплой с миграциями и seed — `./scripts/k8s-deploy.sh` (подставляет тег через сгенерированные kustomization вне git, поэтому новая сборка перекатывает поды без `rollout restart`); проверено с нуля (инструкция и ограничения — [k8s/README.md](k8s/README.md)). Облачного overlay (реестр образов, TLS, управляемый Postgres) нет. Базы в кластере проверяются `pg_isready -U … -d …`, `PGDATA` лежит в подпапке тома. Readiness сервисов — `/ready` (база и ревизия схемы; на чистом кластере поды не готовы, пока не прошли миграции), gateway — `/ready` без проверки сервисов, liveness — `GET /` (60 с неудач до перезапуска), таймаут проб 3 с. Лимита CPU у пяти Deployment нет (троттлинг на 200m растягивал вход до ~2,5 с и валил пробы под нагрузкой), requests CPU и лимиты памяти есть
- В Kubernetes сетевые политики по умолчанию запрещают всё: открыты только DNS, вход от Envoy к фронту и gateway, фронт → gateway, gateway → auth, task, time, task ↔ time (статистика и проверка задачи) и каждый сервис со своими Job → своя база. Сервис не достанет до чужой базы, базы и сервисы не выходят в интернет ([k8s/README.md](k8s/README.md#сетевые-политики))
- Списки задач и проектов в API — постраничные (конверт `{items, total, limit, offset}`, до 200 за запрос), с сортировкой по белому списку и фильтрами (см. «API»); проект задач догружается одним запросом на страницу. Дашборд показывает проекты страницами по 20 (по умолчанию новые сверху), сортировка — по дате создания или названию в обе стороны; по умолчанию только активные, переключатель «Показать архив» — только архивные; кнопка «В архив» / «Восстановить» у проекта шлёт `PATCH {is_active}`. Карточка — первые три активные задачи и их число из того же ответа (`tasks_preview`, `tasks_count`), дашборд делает один запрос списка проектов и ещё один — задач вне проекта для карточки «Без проекта»; задач по проектам не запрашивает. Панель проекта — «Текущие» (`todo`, `in_progress`, `blocked`) и «Выполненные» двумя запросами со своими страницами по 20, сортировка по любому из пяти полей (по умолчанию по созданию, старые сверху), переключатель «Показать архив» и кнопки «В архив» / «Восстановить» у задачи; у архивной задачи нет кнопок таймера и «Выполнена». `PATCH` проекта без `is_active` архив не снимает. Ограничение: вид страниц, сортировки и кнопок — фаза 3.
- Задачи и проекты правятся `PATCH` (merge-patch: нет поля — не трогать, `null` очищает описание, срок и проект задачи, неизвестное поле — `422`; так же и `PATCH` записей времени), `PUT` удалён; название — 1–255 символов после обрезки пробелов, срок — только с часовым поясом. В интерфейсе: «✓», статус при старте таймера, архив и окна «Изменить». У задачи в панели проекта (текущие, выполненные, архив) и на карточке проекта кнопка «Изменить» открывает окно; на `PATCH` уходят только изменённые поля (очищенные описание, срок и проект — `null`, срок — ISO с `Z`), без изменений запроса нет, пустое название — тост без запроса, ошибка сервера — тост с текстом `detail`. В списке проектов окна задачи — «Без проекта», активные проекты владельца задачи (у admin — не чужие, иначе перенос дал бы `400`) и текущий проект, даже архивный; до 200 активных проектов. После сохранения панель и карточки перечитываются (задача, ушедшая в другой проект, пропадает из панели), индикатор идущего таймера показывает новое название. В строке задачи виден срок. Задачи вне проекта: карточка «Без проекта» (свой класс `.no-project-card`, не `.project-card`) всегда первая на дашборде, на любой странице и при любой сортировке, от «Показать архив» проектов не зависит; счётчик и превью — активные задачи без проекта (`GET /api/tasks/tasks?project_id=none&is_active=true&limit=3&sort=created_at`, `total` и `items`), запрос идёт параллельно со списком проектов и перечитывается после тех же действий; ошибка этого запроса — тост, проекты показываются. Кнопок «Изменить» и «В архив» у карточки нет. Панель открывается в режиме без проекта (заголовок «Без проекта», запросы с `project_id=none`, «Добавить задачу» создаёт задачу без `project_id`); остальное, включая «Изменить», как у проекта. У admin панель и карточка показывают задачи всех пользователей, «Добавить задачу» создаёт задачу admin. Заголовок панели (название проекта) раньше не показывался — слот `n-drawer` его не выводит; теперь он в `n-drawer-content`
- В Docker Compose наружу опубликованы только frontend (5173) и gateway (8000), по умолчанию на `127.0.0.1` (`BIND_ADDR`); auth, task, time и базы доступны только внутри сети compose
- Секреты и пароли баз в Docker Compose генерирует `scripts/init-env.sh` (в `.env`, не в git); в Kubernetes секреты лежат в `k8s/overlays/local/app.env` и `db.env` (генерирует `scripts/init-k8s-env.sh`, не в git), пароли в манифестах не зашиты

Известные ограничения (осознанно оставлены, подробнее — [k8s/README.md](k8s/README.md#известные-ограничения)):
- POST и PATCH при перекатке сервиса не повторяются: если запрос ушёл в соединение, которое в ту же миллисекунду закрывает останавливающийся под, клиент получит 502 (порядка одного на несколько тысяч записей под нагрузкой). Таймер и записи можно отправить повторно: старт той же задачи возвращает идущую запись.
- Когда на одном узле kind разом перекатываются все Deployment, узел перегружен, и time может не успеть подключиться к task за 2 с: старт таймера или ручная запись получают 503 «Task service unavailable» (2 из ~10 тыс. запросов в замере). Повтор помогает; проверка на нескольких узлах — в этапе «k8s: продакшен-практики».
- Выданный access-токен нельзя отозвать: отключённый пользователь сохраняет доступ к task и time до 15 минут, снятый admin столько же видит статистику и чужие проекты, задачи и записи в task и time (в auth оба теряют права сразу: роль и `is_active` там берутся из базы). Повышенному до admin права в task и time приходят после refresh токена; фронтенд делает его сам при следующей загрузке страницы (роль в `/me` не совпала с токеном), а API-клиентам нужен refresh или новый вход. Если после успешного refresh повторный запрос снова получил 401, выход случится на следующем 401.
- Замороженный процесс базы (`docker pause`) не обрывается таймаутами: запрос висит, пока база не оживёт, readiness снимает под с трафика.
- Пользователя нельзя удалить, только отключить; журнал смены роли и отключения (`user_audit`) есть только в базе auth, API и экрана для него нет.
- Зарегистрирован ли email, видно по `register` (на занятый адрес — 400); вход этого не выдаёт: неизвестный email считается и отвечает так же.
- Зная чужой email, можно пятью неверными паролями закрыть владельцу вход на 15 минут (вечной блокировки нет; уже выданные токены и refresh продолжают работать).
- При выкатке версии со счётчиком входов попытки, попавшие в старые поды (их несколько секунд после миграции), не считаются.
- `PUT` задач и проектов заменён на `PATCH` без переходного периода: открытая до выкатки вкладка со старым фронтендом на «✓», «В архив» / «Восстановить» и смене статуса при старте таймера получает `405` (тост «Method Not Allowed», задача не меняется), после перезагрузки страницы работает.
- Ответ списков задач и проектов сменился с массива на конверт без переходного слоя: открытая до выкатки вкладка со старым фронтендом при следующей загрузке списка показывает «Ошибка загрузки проектов», после перезагрузки страницы работает.
- Пересечения записей времени не проверяются; записи времени удалённых задач остаются (идущий таймер такой задачи фронтенд показывает как «задача удалена», стоп работает).

## Планы

- Серверный таймер сделан: API таймера и записей (ручные, правка, удаление, список с фильтрами), статистика, проверка задачи у task-service, фронтенд на серверном таймере, схема переведена на новые поля без остановки сервиса. Интерфейс записей времени — позже
- Управление пользователями для admin сделано: API и страница `/users` (список, фильтры, поиск, страницы, смена роли, отключение, журнал прав в базе), email и имя в статистике, роль после смены без повторного входа; вид страницы и колонок статистики — позже
- Страницы, сортировка и архив в интерфейсе сделаны (вид — позже). Правка задач и проектов в API — `PATCH` (merge-patch, вынос задачи из проекта) вместо `PUT`. Окна правки задачи и проекта и задачи вне проекта (карточка «Без проекта») в интерфейсе сделаны (вид — позже). Поведение этапа 2.4 + 2.5 готово. Этап 2.6 (rate limiting): keep-alive и счётчик неудачных входов по email сделаны, дальше закрытие `:8000` в compose и лимит на входе
- Kubernetes: облачный overlay и HPA (плавная остановка подов — `preStop`, сделана)
- Отчёты по времени и экспорт
- Лимиты запросов, логирование, метрики

## Лицензия

Лицензия пока не выбрана.
