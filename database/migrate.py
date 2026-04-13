import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from database.connection import Base, engine
from database.models import *


EXPECTED_COLUMNS = {
    "users": {
        "username": "VARCHAR(100)",
        "language": "VARCHAR(10)",
        "created_at": "TIMESTAMP",
    },
    "companies": {
        "name": "VARCHAR(255)",
        "company_number": "VARCHAR(50)",
        "registered_address": "TEXT",
        "status": "VARCHAR(50)",
        "score": "INTEGER",
        "website_domain": "VARCHAR(255)",
        "contact_email": "VARCHAR(255)",
        "phone_number": "VARCHAR(50)",
        "incorporation_date": "DATE",
        "last_updated": "TIMESTAMP",
        "created_at": "TIMESTAMP",
    },
    "user_checks": {
        "user_id": "INTEGER",
        "company_id": "INTEGER",
        "contract_number": "VARCHAR(100)",
        "contract_date": "DATE",
        "extracted_company_name": "VARCHAR(255)",
        "extracted_company_number": "VARCHAR(50)",
        "extracted_address": "TEXT",
        "website_domain": "VARCHAR(255)",
        "contract_template_hash": "TEXT",
        "total_score": "INTEGER",
        "safety_rating": "VARCHAR(20)",
        "detailed_scores": "JSON",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
    "suspicious_companies": {
        "company_name": "VARCHAR(255)",
        "company_number": "VARCHAR(50)",
        "evidence": "TEXT",
        "source": "VARCHAR(100)",
        "status": "VARCHAR(20)",
        "website_domain": "VARCHAR(255)",
        "registered_address": "TEXT",
        "contact_phone": "VARCHAR(50)",
        "contact_email": "VARCHAR(255)",
        "added_by": "INTEGER",
        "verified_by": "INTEGER",
        "verified_at": "TIMESTAMP",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    },
    "suspicious_entities": {
        "email_domain": "VARCHAR(255)",
        "phone_number": "VARCHAR(50)",
        "recruiter_name": "VARCHAR(255)",
        "contract_template_hash": "VARCHAR(64)",
        "source": "VARCHAR(100)",
        "created_at": "TIMESTAMP",
    },
}


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
        for table, columns in EXPECTED_COLUMNS.items():
            for column, col_type in columns.items():
                await _ensure_column(conn, table, column, col_type)
    print("SQLite database and tables created successfully at: database/app.db")


if __name__ == "__main__":
    asyncio.run(init_models())
