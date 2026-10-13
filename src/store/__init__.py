"""Dated legal store (SQLite). See docs/store_schema.md."""
from .db import connect, init_db, DEFAULT_DB_PATH  # noqa: F401
from .resolve import get_rule_on_date  # noqa: F401
