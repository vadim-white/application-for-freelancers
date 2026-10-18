# uv закреплён по версии и digest: тег можно перевесить на другой образ, digest — нет
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv

# Этап сборки: зависимости строго по uv.lock в venv вне /app. uv остаётся только в этом этапе
FROM python:3.14-slim AS deps
COPY --from=uv /uv /bin/uv
# .pyc зависимостей при сборке (как делал pip): без них импорт при лимите CPU 200m вдвое дольше;
# Python из образа, не скачивать; copy — кэш смонтирован отдельно от venv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY auth-service/pyproject.toml auth-service/uv.lock ./
# --locked: ошибка, если uv.lock не совпадает с pyproject.toml; кэш uv — в cache mount, в слой не попадает
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

FROM python:3.14-slim

# без .pyc для кода приложения и с немедленным выводом логов;
# venv первым в PATH — uvicorn, alembic и python берутся из него
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"

# venv из этапа сборки: тот же базовый образ, поэтому путь к интерпретатору в venv совпадает
COPY --from=deps /opt/venv /opt/venv

WORKDIR /app

# Копирование приложения
COPY auth-service .

# Непривилегированный пользователь; код и venv принадлежат root и процессу доступны только на чтение.
# USER числом, а не именем: kubelet проверяет runAsNonRoot только по числовому UID (имя не резолвит)
RUN useradd --system --uid 10001 --no-create-home app
USER 10001

# Запуск сервиса
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
