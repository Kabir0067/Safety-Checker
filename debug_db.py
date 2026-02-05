
import asyncio
import os
from database.connection import AsyncSessionLocal
from database.models import User, UserCheck
from sqlalchemy import select
from database.queries import get_lang, add_user_check, add_company

async def debug_db():
    print("--- Debugging DB ---")
    async with AsyncSessionLocal() as session:
        # 1. Check Users
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f"Total Users: {len(users)}")
        for u in users:
            print(f"User: {u.telegram_id}, Lang: {u.language}, Username: {u.username}")

        # 2. Check UserChecks
        result = await session.execute(select(UserCheck))
        checks = result.scalars().all()
        print(f"Total Checks: {len(checks)}")
        for c in checks:
             print(f"Check ID: {c.id}, UserID: {c.user_id}, Company: {c.extracted_company_name}")

if __name__ == "__main__":
    try:
        asyncio.run(debug_db())
    except Exception as e:
        print(f"Error: {e}")
