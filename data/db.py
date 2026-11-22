import os
import mysql.connector
from mysql.connector import pooling, Error

# Load DB configuration from environment variables (or defaults for local dev)
_dbconfig = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "kisaan_suvidha"),
    "charset": "utf8mb4",
    "collation": "utf8mb4_unicode_ci",
}

# Lazy-initialised connection pool – created on first request to avoid import‑time failures
_pool = None

def _init_pool():
    """Create the MySQL connection pool.
    Raises a clear RuntimeError if connection parameters are invalid.
    """
    try:
        return pooling.MySQLConnectionPool(pool_name="kisaan_pool", pool_size=5, **_dbconfig)
    except Error as e:
        raise RuntimeError(
            f"Unable to initialise MySQL connection pool: {e}. "
            "Check that MySQL is running and DB_* environment variables are set."
        )

def get_db():
    """Return a MySQL connection from the pool.
    The pool is created on first call, so the module can be imported even when the DB
    is not yet configured (useful for running the app without a DB during UI prototyping).
    Caller should close the connection after use.
    """
    global _pool
    if _pool is None:
        _pool = _init_pool()
    return _pool.get_connection()
