import logging
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .db import engine

logger = logging.getLogger(__name__)

# от файла, а не от текущего каталога: uvicorn и pytest запускаются из разных мест
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def load_revisions(config: Config) -> tuple[str, frozenset[str]]:
    """head миграций из образа и все его предки (без самого head)."""
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    older = frozenset(s.revision for s in script.iterate_revisions(head, "base")) - {head}
    return head, older


HEAD, OLDER = load_revisions(Config(str(ALEMBIC_INI)))

router = APIRouter()


def not_ready(reason: str, detail: str = "") -> JSONResponse:
    # текст ошибки драйвера только в лог: в нём адрес базы
    logger.warning("not ready: %s %s", reason, detail)
    return JSONResponse(status_code=503, content={"ready": False, "reason": reason})


# Синхронный: запрос к БД блокирующий, FastAPI выполнит его в пуле потоков.
# Незнакомая ревизия — 200: при expand/contract миграция применяется раньше выката кода,
# и старые поды не должны выпадать из балансировки
@router.get("/ready")
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            current = MigrationContext.configure(conn).get_current_revision()
    except SQLAlchemyError as exc:
        return not_ready("database unavailable", str(exc).splitlines()[0])
    if current is None:
        return not_ready("schema not migrated")
    if current in OLDER:
        return not_ready(f"schema revision {current} is older than code {HEAD}")
    return {"ready": True}
