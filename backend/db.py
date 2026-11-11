
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# The project keeps its private environment file at the repository root.
# Explicit host environment variables remain higher priority than this file.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def get_db_connection():
    """Create a direct connection to PostgreSQL."""
    return psycopg.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "ubdtce_evoting"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5,
    )


if __name__ == "__main__":
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database(), version();")
                database, version = cur.fetchone()
                print(f"Connected to database: {database}")
                print(f"PostgreSQL version: {version.split(',')[0]}")
    except Exception as exc:
        print(f"Database connection failed: {exc}")
        raise SystemExit(1)
