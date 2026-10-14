# Freelance Time Tracker

Трекер задач и рабочего времени на микросервисной архитектуре. Бэкенд написан на FastAPI, фронтенд на Vue 3. Проект задуман как полноценная open-source альтернатива готовым решениям на Django: с раздельными сервисами, единой точкой входа и деплоем в контейнерах и Kubernetes.

Проект находится в активной разработке. Раздел [Текущее состояние](#текущее-состояние) описывает, что уже работает, а что ещё нет.

## Возможности

- Регистрация и вход по email и паролю, JWT (access и refresh токены), роли `user` и `admin`
- Проекты и задачи: создание, просмотр, редактирование, удаление, смена статуса
- Таймер на задачу: старт, пауза, остановка, запись затраченного времени
- Статистика по пользователям для администратора: выполненные задачи и затраченное время
- Профиль пользователя

## Архитектура

```
                      Frontend (Vue 3, :5173)
                               |
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
| frontend | 5173 | SPA на Vue 3, TypeScript, Pinia, Naive UI |

У каждого сервиса своя база данных, сервисы не ходят в чужие таблицы. Task Service обращается к Time Service по HTTP, когда собирает статистику.

## Стек

- Python 3.11, FastAPI, SQLAlchemy 2, Pydantic 2
- PostgreSQL 15 (в Docker), SQLite для локальной разработки без контейнеров
- JWT (python-jose), хеширование паролей через bcrypt
- Vue 3, TypeScript, Pinia, Vue Router, Axios, Vite, Naive UI
- Docker, Docker Compose, Kubernetes

## Быстрый старт

### Через Docker Compose

Нужны Docker и Docker Compose.

```bash
git clone https://github.com/vadim-white/application-for-freelancers.git
cd application-for-freelancers
docker compose up --build
```

После запуска:

- приложение: http://localhost:5173
- gateway: http://localhost:8000
- документация сервисов (Swagger) доступна на `/docs` у каждого сервиса. В compose наружу опубликованы только gateway и frontend, поэтому Swagger остальных сервисов открывается при локальном запуске

В `docker-compose.yml` включён `SEED_TEST_USERS=true`, поэтому при старте auth-service создаёт тестовых пользователей (если их ещё нет). По умолчанию, без этой переменной, тестовые пользователи не создаются:

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

Нужны Python 3.11+ и Node.js 20+. Каждый сервис запускается в отдельном терминале со своим виртуальным окружением. Таблицы создаются автоматически при старте. По умолчанию сервисы используют SQLite-файлы в своих папках.

Перед первым запуском скопируйте в каждой папке сервиса и в `frontend/login_page` файл `.env.example` в `.env`. В `.env` всех четырёх бэкенд-сервисов впишите один и тот же `SECRET_KEY`, без него сервисы не стартуют. Сгенерировать ключ: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Остальные значения из примеров подходят для локального запуска.

```bash
# auth-service
cd auth-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# task-service
cd task-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002

# time-service
cd time-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003

# gateway-service
cd gateway-service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend/login_page
npm install
npm run dev
```

Адрес gateway для фронтенда задаётся переменной `VITE_API_BASE` в `frontend/login_page/.env`. Если фронтенд открыт не на `http://localhost:5173`, добавьте его адрес в `CORS_ORIGINS` gateway.

### Тесты

Тесты есть у gateway, auth-service, task-service и time-service. Им не нужны запущенные сервисы: внешние HTTP-вызовы (gateway → сервисы, task → time) подменяются в тестах, базы — временная SQLite. Запуск в том же образе Python, что и у сервиса (`<service>` — `gateway-service`, `auth-service`, `task-service` или `time-service`):

```bash
docker run --rm -v "$PWD/<service>":/src:ro python:3.11-slim sh -c \
  "cp -r /src /app && cd /app && rm -rf .env .venv && pip install -q -r requirements.txt -r requirements-dev.txt && python -m pytest -q"
```

### Kubernetes

Манифесты лежат в [k8s/](k8s/).

```bash
kubectl apply -f k8s/
kubectl get pods -n <namespace>
```

Имя namespace указано в [k8s/00-namespace.yaml](k8s/00-namespace.yaml).

## Конфигурация

Основные переменные окружения. Все переменные с описанием собраны в файлах `.env.example` в папке каждого сервиса и в `frontend/login_page`.

| Переменная | Где используется | Описание |
|------------|------------------|----------|
| `DATABASE_URL` | auth, task, time | Строка подключения SQLAlchemy |
| `SECRET_KEY` | все сервисы | Ключ подписи JWT, должен быть одинаковым везде. Обязателен: без него сервисы не стартуют |
| `ALGORITHM` | все сервисы | Алгоритм подписи, по умолчанию `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | auth | Время жизни access-токена |
| `SEED_TEST_USERS` | auth | `true` — создать тестовых пользователей при старте, только для разработки. По умолчанию `false` |
| `AUTH_URL`, `TASK_URL`, `TIME_URL` | gateway | Адреса внутренних сервисов |
| `CORS_ORIGINS` | gateway | Адреса фронтенда, которым разрешены запросы из браузера, через запятую. По умолчанию `http://localhost:5173,http://127.0.0.1:5173`. Внутренние сервисы CORS не настраивают: браузер обращается только к gateway |
| `TIME_SERVICE_URL` | task | Адрес Time Service для сбора статистики |
| `VITE_API_BASE` | frontend | Адрес gateway |

Значения из `docker-compose.yml` годятся только для разработки. Перед любым реальным деплоем замените `SECRET_KEY` и пароли баз данных.

## API

Все запросы идут через gateway с префиксом `/api`. Все эндпоинты, кроме `/api/auth/register`, `/api/auth/login` и `/api/auth/refresh`, требуют заголовок `Authorization: Bearer <access-токен>`.

| Метод | Путь | Описание |
|-------|------|----------|
| POST | `/api/auth/register` | Регистрация |
| POST | `/api/auth/login` | Вход, возвращает access и refresh токены |
| POST | `/api/auth/refresh` | Обновление access-токена |
| GET | `/api/auth/me` | Текущий пользователь |
| GET, POST | `/api/tasks/projects` | Список и создание проектов (создание только для admin) |
| GET, PUT, DELETE | `/api/tasks/projects/{id}` | Проект (изменение и удаление только для admin) |
| GET, POST | `/api/tasks/tasks` | Список и создание задач |
| GET, PUT, DELETE | `/api/tasks/tasks/{id}` | Задача |
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
├── k8s/                 манифесты Kubernetes
├── docker-compose.yml
└── helm-values.yaml
```

## Текущее состояние

Проект работает как рабочий прототип, но не готов к продакшену. Что уже сделано и какие ограничения предстоит закрыть:

- Gateway проверяет Bearer access-токен (подпись, срок `exp`, тип `access`) для всех путей, кроме `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/health` и `/`. Без токена или с неверным токеном ответ 401, неизвестные пути 404. Клиентские заголовки `X-User-*` затираются, gateway ставит свои `X-User-Id` и `X-User-Role` из токена
- task-service и time-service сами проверяют access-токен так же, как gateway (подпись, `exp`, тип `access`), и не доверяют заголовкам `X-User-*`: без токена 401, в том числе при обращении в обход gateway. Статистика по пользователям только для admin; task-service при сборе статистики передаёт в time-service токен пользователя. В time-service `user_id` записи берётся только из токена (поле `user_id` в теле игнорируется), пользователь видит только свои записи, admin — все
- Задачи и проекты пока видны всем авторизованным пользователям: у них ещё нет поля владельца (появится с миграциями)
- auth-service: роль в access-токене берётся из БД и при входе, и при обновлении токена; отключённый (`is_active=false`) или удалённый пользователь не может войти, обновить токен и получить `/api/auth/me`. Ключ `SECRET_KEY` обязателен, тестовые пользователи создаются только при `SEED_TEST_USERS=true`
- `.dockerignore` исключает `.env`, `*.db`, `.venv`, `node_modules` во всех папках, локальные настройки и базы больше не попадают в образы
- `SECRET_KEY` обязателен во всех сервисах. CORS настроен только в gateway и разрешает лишь адреса из `CORS_ORIGINS`
- Фронтенд сам обновляет access-токен: на ответ 401 он один раз запрашивает `/api/auth/refresh` (параллельные запросы ждут один общий refresh) и повторяет запрос. Если refresh не удался, токены удаляются и открывается страница входа. Refresh-токен живёт 7 дней и не обновляется, после этого нужно войти заново
- Кнопка «Выполнено» в списке задач проекта ставит статус `done`, а не удаляет задачу. Выполненные задачи показываются отдельным сворачиваемым блоком под текущими
- В Docker Compose все сервисы работают с PostgreSQL. В task-service и time-service закреплена только версия SQLAlchemy (2.1 по умолчанию требует драйвер `psycopg` v3), остальные зависимости этих сервисов не закреплены
- Нет миграций, таблицы создаются через `create_all` при старте
- Автотесты (pytest) есть у всех бэкенд-сервисов, CI нет
- Фронтенд запускается в dev-режиме, production-сборки нет
- В Kubernetes нет Ingress и автомасштабирования, у всех сервисов одна реплика
- Нет пагинации, фильтрации и сортировки задач
- Секреты и пароли в конфигурации заданы значениями для разработки

## Планы

- Владелец у задач и проектов, доступ только к своим данным (admin видит всё)
- Закреплённые версии зависимостей во всех сервисах, миграции через Alembic
- Серверное состояние таймера: запуск, пауза и остановка на бэкенде, защита от параллельных таймеров
- Тесты (pytest) для всех сервисов и CI
- Production-сборка фронтенда за nginx
- Ingress, HPA, health и readiness probes в Kubernetes
- Отчёты по времени и экспорт
- Лимиты запросов, логирование, метрики

## Лицензия

Лицензия пока не выбрана.
