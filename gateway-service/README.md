# Gateway Service (gateway-service)

Единая точка входа `/api`: проверяет JWT и проксирует запросы в auth, task и time. Своей базы нет. Порт — 8000. OpenAPI: http://127.0.0.1:8000/docs

Один `httpx.AsyncClient` на процесс (создаётся в `lifespan`, `app/main.py`). Таймауты запроса к сервису: подключение 5 с, остальное 30 с; сервис недоступен — 502, не ответил вовремя — 504. Ответ сервиса отдаётся потоком без изменений тела; hop-by-hop заголовки, а также `date` и `server` сервиса (их ставит uvicorn gateway) не пересылаются. Подробнее — [«Архитектура» в корневом README](../README.md#архитектура).

## Локальный запуск

1. Скопируйте `.env.example` в `.env`. `SECRET_KEY` должен совпадать во всех бэкенд-сервисах; `AUTH_URL`, `TASK_URL`, `TIME_URL` — адреса сервисов (в примере 8001, 8002, 8003).
2. Установите зависимости (нужен uv, Python 3.14 он поставит сам; `.venv` создаётся в папке сервиса):
   ```bash
   uv sync
   ```
3. Запустите сервис:
   ```bash
   uv run uvicorn app.main:app --reload --port 8000
   ```

Проверка: `GET http://127.0.0.1:8000/health` — опрашивает auth, task и time параллельно (таймаут 2 с на каждый), они должны быть уже запущены.

`GET /ready` — всегда 200 `{"ready": true}`, сервисы не опрашивает: иначе один упавший сервис снимал бы с трафика весь gateway (readiness-проба Kubernetes и healthcheck compose).

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны: общий клиент в тестах подменяется клиентом на `httpx.MockTransport` (`app.dependency_overrides`, фикстура `mock_upstream` в `tests/conftest.py`). Подробнее — [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.
