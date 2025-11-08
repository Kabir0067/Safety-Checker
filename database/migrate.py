import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from database.connection import Base, engine
from database.models import *


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ SQLite database and tables created successfully at: database/app.db")


if __name__ == "__main__":
    asyncio.run(init_models())
