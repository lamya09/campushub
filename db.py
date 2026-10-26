"""
db.py — MySQL connection pool helper for CampusHub.

Reads connection settings from environment variables (loaded by app.py
via python-dotenv) so credentials never appear in source code.
"""

import os
import mysql.connector
from mysql.connector import pooling, Error

# ---------------------------------------------------------------------------
# Pool configuration (created once on import)
# ---------------------------------------------------------------------------

_pool: pooling.MySQLConnectionPool | None = None


def _build_pool() -> pooling.MySQLConnectionPool:
    """Create and return the connection pool."""
    config = {
        "host": os.environ.get("DB_HOST", "127.0.0.1"),
        "port": int(os.environ.get("DB_PORT", 3306)),
        "database": os.environ.get("DB_NAME", "CampusHub"),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "charset": "utf8mb4",
        "collation": "utf8mb4_general_ci",
        "pool_name": "campushub_pool",
        "pool_size": 5,
        "pool_reset_session": True,
        "autocommit": False,
    }
    return pooling.MySQLConnectionPool(**config)


def get_pool() -> pooling.MySQLConnectionPool:
    """Return the singleton connection pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


def get_connection():
    """
    Obtain a pooled connection.

    Usage:
        conn = get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            ...
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()   # returns connection to pool
    """
    return get_pool().get_connection()
