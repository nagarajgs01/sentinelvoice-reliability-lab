from __future__ import annotations

from time import perf_counter

import httpx

from .config import settings


class OllamaService:
    async def complete(self, model: str, prompt: str) -> tuple[str, float]:
        if not prompt.strip():
            raise ValueError("Prompt is empty")
        started = perf_counter()
        timeout = httpx.Timeout(180.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/chat",
                json={
                    "model": model,
                    "stream": False,
                    "think": False,
                    "keep_alive": "10m",
                    "options": {"temperature": 0, "num_predict": 160},
                    "messages": [
                        {"role": "system", "content": "Answer clearly and concisely for a spoken voice response."},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            response.raise_for_status()
        return response.json()["message"]["content"].strip(), perf_counter() - started


ollama_service = OllamaService()
