# В образе Playwright только браузеры, без uv и пакета playwright: uv — бинарником из его образа.
# Версия и digest закреплены: тег можно перевесить, digest — нет.
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

# Python 3.12 и браузеры релиза 1.64.1; digest — мультиархитектурный индекс (amd64 и arm64)
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble@sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031
COPY --from=uv /uv /bin/uv
# venv вне каталога с тестами (тесты монтирует run.sh); Python из образа, не скачивать
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PATH="/opt/venv/bin:$PATH"
WORKDIR /e2e
COPY pyproject.toml uv.lock .python-version ./
# --locked: ошибка, если uv.lock не совпадает с pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project
