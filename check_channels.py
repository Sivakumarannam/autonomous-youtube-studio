# check_channels.py

import asyncio
from sqlalchemy import text

from app.database.connection import async_session_maker

async def main():
    async with async_session_maker() as session:

        result = await session.execute(
            text("SELECT id,name FROM channels")
        )

        rows = result.fetchall()

        print("\nCHANNELS:\n")

        for row in rows:
            print(row)

asyncio.run(main())