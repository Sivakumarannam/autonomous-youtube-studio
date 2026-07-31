# check_topics.py

import asyncio
from sqlalchemy import text

from app.database.connection import async_session_maker

async def main():
    async with async_session_maker() as session:

        result = await session.execute(
            text("SELECT id,title,channel_id FROM topics")
        )

        rows = result.fetchall()

        print("\nTOPICS:\n")

        for row in rows:
            print(row)

asyncio.run(main())