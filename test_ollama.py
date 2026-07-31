import sys
import asyncio

sys.stdout.reconfigure(encoding="utf-8")

from app.llm_providers.factory import get_llm_provider


async def main():
    provider = get_llm_provider()

    result = await provider.generate_text(
        "Give me 5 YouTube topics about DevOps"
    )

    print(result)


asyncio.run(main())