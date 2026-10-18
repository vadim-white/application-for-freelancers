# Образ для e2e: браузеры из образа Playwright + Python-зависимости строго по uv.lock.
# В образе Playwright нет ни uv, ни pip-пакета playwright (только браузеры). uv берём бинарником
# из его образа, как в Dockerfile сервисов; версия и digest закреплены (тег можно перевесить, digest — нет).
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv

# Python 3.12 и браузеры релиза 1.63.0; digest — мультиархитектурный индекс (amd64 и arm64)
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble@sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0
COPY --from=uv /uv /bin/uv
# venv вне каталога с тестами (тесты монтирует run.sh); Python из образа, не скачивать
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PATH="/opt/venv/bin:$PATH"
WORKDIR /e2e
COPY pyproject.toml uv.lock .python-version ./
# --locked: ошибка, если uv.lock не совпадает с pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
