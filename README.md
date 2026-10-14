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

При первом старте auth-service создаёт тестовых пользователей:

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

Адрес gateway для фронтенда задаётся переменной `VITE_API_BASE` в `frontend/login_page/.env`.

### Kubernetes

Манифесты лежат в [k8s/](k8s/).

```bash
kubectl apply -f k8s/
kubectl get pods -n <namespace>
```

Имя namespace указано в [k8s/00-namespace.yaml](k8s/00-namespace.yaml).

## Конфигурация

Основные переменные окружения:

| Переменная | Где используется | Описание |
|------------|------------------|----------|
| `DATABASE_URL` | auth, task | Строка подключения SQLAlchemy |
| `SECRET_KEY` | все сервисы | Ключ подписи JWT, должен быть одинаковым везде |
| `ALGORITHM` | все сервисы | Алгоритм подписи, по умолчанию `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | auth | Время жизни access-токена |
| `AUTH_URL`, `TASK_URL`, `TIME_URL` | gateway | Адреса внутренних сервисов |
| `TIME_SERVICE_URL` | task | Адрес Time Service для сбора статистики |
| `VITE_API_BASE` | frontend | Адрес gateway |

Значения из `docker-compose.yml` годятся только для разработки. Перед любым реальным деплоем замените `SECRET_KEY` и пароли баз данных.

## API

Все запросы идут через gateway с префиксом `/api`.

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
| GET | `/api/tasks/statistics/users` | Статистика по пользователям |
| GET, POST | `/api/time/time-entries` | Записи о времени |
| GET | `/api/time/statistics/users` | Статистика времени по пользователям |

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

Проект работает как рабочий прототип, но не готов к продакшену. Известные ограничения, которые предстоит закрыть:

- Gateway пока не проверяет JWT: проверка в `gateway-service/app/middleware.py` отключена, токен разбирается внутри сервисов. Это значит, что часть эндпоинтов доступна без авторизации
- Time Service использует SQLite независимо от `DATABASE_URL`, хотя в compose для него поднят PostgreSQL
- Нет миграций, таблицы создаются через `create_all` при старте
- Нет автотестов
- Фронтенд запускается в dev-режиме, production-сборки нет
- В Kubernetes нет Ingress и автомасштабирования, у всех сервисов одна реплика
- Нет пагинации, фильтрации и сортировки задач
- Секреты и пароли в конфигурации заданы значениями для разработки

## Планы

- Проверка JWT и проброс `X-User-Id`, `X-User-Role` на уровне gateway
- Единая работа с PostgreSQL во всех сервисах, миграции через Alembic
- Серверное состояние таймера: запуск, пауза и остановка на бэкенде, защита от параллельных таймеров
- Тесты (pytest) и CI
- Production-сборка фронтенда за nginx
- Ingress, HPA, health и readiness probes в Kubernetes
- Отчёты по времени и экспорт
- Лимиты запросов, логирование, метрики

## Лицензия

Лицензия пока не выбрана.
