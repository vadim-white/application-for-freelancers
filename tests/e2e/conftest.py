"""Фикстуры e2e: адрес фронта, метка прогона, контекст браузера со страницей и записью сети.

Адрес — E2E_BASE_URL (по умолчанию http://127.0.0.1:5173, compose; kind — http://127.0.0.1:8080).
"""

import os
import time
import uuid

import pytest

from helpers import NAVIGATION_TIMEOUT_MS, TIMEOUT_MS, Net, Session


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5173").rstrip("/")


@pytest.fixture(scope="session")
def run_label() -> str:
    """Метка прогона в именах создаваемых объектов: e2e не опирается на данные других проверок."""
    return f"e2e-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


@pytest.fixture
def open_session(new_context):
    """Новый контекст браузера (свой localStorage — свой пользователь) со страницей и записью сети.

    new_context из pytest-playwright: base_url подставляет сам (из фикстуры base_url выше), скриншот
    и trace упавшего теста сохраняет и для этих контекстов.
    """

    def _open() -> Session:
        context = new_context()
        context.set_default_timeout(TIMEOUT_MS)
        context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
        page = context.new_page()
        return Session(context, page, Net().attach(page))

    return _open
