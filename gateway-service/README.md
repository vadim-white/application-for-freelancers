# Gateway Service (gateway-service)

Единая точка входа `/api`: проверяет JWT и проксирует запросы в auth, task и time. Своей базы нет. Порт — 8000. OpenAPI: http://127.0.0.1:8000/docs

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

Проверка: `GET http://127.0.0.1:8000/health` — опрашивает auth, task и time, которые должны быть уже запущены.

## Тесты

```bash
uv run pytest -q
```

Запущенные сервисы не нужны: обращения к ним в тестах подменяются. Подробнее — [«Тесты» в корневом README](../README.md#тесты).

## Переменные окружения

Локально — из `.env` (шаблон — `.env.example`). В Docker Compose и Kubernetes переменные задаются в `docker-compose.yml` и `k8s/`.
