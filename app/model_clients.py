from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from app import toy_target


class ModelClient(Protocol):
    def generate(self, prompt: str, **kwargs) -> str:
        ...


@dataclass
class ToyModelClient:
    strategy: str = "structured"

    def generate(self, prompt: str, **kwargs) -> str:
        case = kwargs.get("case") or {
            "question": prompt,
            "reference_answer": "Réponse de démonstration.",
            "expected_concepts": [],
            "requires_code": False,
        }
        return toy_target.answer(case, self.strategy)


@dataclass
class GroqModelClient:
    strategy: str = "structured"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.3
    max_retries: int = 3
    retry_delay: float = 5.0

    def generate(self, prompt: str, **kwargs) -> str:
        try:
            import requests
            import time
        except ImportError as exc:
            raise RuntimeError("Install the requests package: pip install requests") from exc

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set.")

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.temperature,
                    },
                    timeout=30,
                )
                # 429 = rate limit → attendre puis réessayer
                if response.status_code == 429:
                    wait = self.retry_delay * (attempt + 1)
                    time.sleep(wait)
                    continue
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                # Réponse trop courte = probablement un refus ou erreur silencieuse
                if len(content.strip()) < 20 and attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                return content
            except Exception:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
        raise RuntimeError("Groq API : max retries atteint.")


@dataclass
class OpenAIResponsesClient:
    model: str = "gpt-4o-mini"
    temperature: float = 0.2

    def generate(self, prompt: str, **kwargs) -> str:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install the openai package before using OpenAIResponsesClient.") from exc

        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not set.")

        client = OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return response.choices[0].message.content
