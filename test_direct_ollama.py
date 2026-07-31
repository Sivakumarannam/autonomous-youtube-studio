import asyncio
import httpx


async def main():
    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen3:latest",
                "messages": [
                    {
                        "role": "user",
                        "content": "Give me 5 DevOps YouTube topics"
                    }
                ],
                "stream": False
            }
        )

        print(response.status_code)
        data = response.json()

        content = data["message"]["content"]

        print(content.encode("ascii", errors="ignore").decode())


asyncio.run(main())