"""
Re-exports the SQLAlchemy declarative Base so every model can import
from a single canonical location without circular-import issues.

All models import:
    from app.database.models.base import Base

Alembic's env.py imports:
    from app.database.models.base import Base
    import app.database.models  # noqa: F401 — registers all mappers
"""
from app.database.connection import Base

__all__ = ["Base"]