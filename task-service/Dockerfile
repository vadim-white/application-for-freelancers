# uv закреплён по версии и digest: тег можно перевесить на другой образ, digest — нет
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

# uv остаётся только в этапе сборки, в итоговый образ не попадает
FROM python:3.14-slim AS deps
COPY --from=uv /uv /bin/uv
# .pyc зависимостей — при сборке: в контейнере их не записать, и каждый старт компилировал бы импорт заново;
# copy — кэш смонтирован отдельно от venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY task-service/pyproject.toml task-service/uv.lock ./
# --locked: ошибка, если uv.lock не совпадает с pyproject.toml; кэш uv — в cache mount, в слой не попадает
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.14-slim

# логи без буфера: сразу видны в docker logs и kubectl logs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"

# venv из этапа сборки: тот же базовый образ, поэтому путь к интерпретатору в venv совпадает
COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

# Только рантайм: alembic.ini и migrations/ нужны Job и контейнерам миграций на этом же образе
COPY task-service/app ./app
COPY task-service/migrations ./migrations
COPY task-service/alembic.ini ./

# Непривилегированный пользователь; код и venv принадлежат root и процессу доступны только на чтение.
# USER числом, а не именем: kubelet проверяет runAsNonRoot только по числовому UID (имя не резолвит)
RUN useradd --system --uid 10001 --no-create-home app
USER 10001

# после SIGTERM до 20 с на начатые запросы: вместе с preStop (5 с) укладывается в grace k8s (30 с).
# Простаивающее соединение закрывает клиент (Envoy через 60 с, httpx через 5 с), а не сервер: иначе запрос
# клиента может уйти в соединение, которое сервер как раз закрывает, — Envoy отдаст 503 и POST не повторит.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--timeout-graceful-shutdown", "20", \
     "--timeout-keep-alive", "75"]
