import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from database.connection import Base, engine
from database.models import *


async def _column_exists(conn, table: str, column: str) -> bool:
    result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    cols = [row[1] for row in result.fetchall()]
    return column in cols


async def _ensure_column(conn, table: str, column: str, col_type: str) -> None:
    if not await _column_exists(conn, table, column):
        await conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_column(conn, "companies", "incorporation_date", "DATE")
        await _ensure_column(conn, "user_checks", "contract_template_hash", "TEXT")
    print("SQLite database and tables created successfully at: database/app.db")


if __name__ == "__main__":
    asyncio.run(init_models())
