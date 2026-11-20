# Clients pour interroger les modèles : un faux modèle local (pour les tests),
# l'API Groq (Llama 3.3 70B) et l'API OpenAI. Tous exposent la même méthode generate().

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from app import toy_target


# Interface commune : n'importe quel client qui possède generate(prompt) -> str convient.
# Cela permet de changer de modèle sans modifier le code d'évaluation.
class ModelClient(Protocol):
    def generate(self, prompt: str, **kwargs) -> str:
        ...


# Faux modèle déterministe : il ne fait aucun appel réseau et renvoie des réponses
# préfabriquées par toy_target. Sert au smoke test et à la CI (pas de clé API nécessaire).
@dataclass
class ToyModelClient:
    strategy: str = "structured"

    def generate(self, prompt: str, **kwargs) -> str:
        # Si aucun cas de test n'est fourni, on en fabrique un minimal à partir du prompt.
        case = kwargs.get("case") or {
            "question": prompt,
            "reference_answer": "Réponse de démonstration.",
            "expected_concepts": [],
            "requires_code": False,
        }
        return toy_target.answer(case, self.strategy)


# Client pour l'API Groq (compatible avec le format OpenAI).
# Gère les limites de débit (erreur 429) et les réponses vides en réessayant.
@dataclass
class GroqModelClient:
    strategy: str = "structured"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.3  # faible = réponses plus stables d'un appel à l'autre
    max_retries: int = 3  # nombre maximal de tentatives par question
    retry_delay: float = 5.0  # attente de base (en secondes) entre deux tentatives

    def generate(self, prompt: str, **kwargs) -> str:
        # Imports faits ici pour que le reste du projet fonctionne sans "requests" installé.
        try:
            import requests
            import time
        except ImportError as exc:
            raise RuntimeError("Install the requests package: pip install requests") from exc

        # La clé API est lue dans les variables d'environnement (jamais écrite dans le code).
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
                # (attente croissante : 5 s, puis 10 s, puis 15 s)
                if response.status_code == 429:
                    wait = self.retry_delay * (attempt + 1)
                    time.sleep(wait)
                    continue
                # Toute autre erreur HTTP (401, 500...) lève une exception.
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                # Réponse trop courte = probablement un refus ou erreur silencieuse
                if len(content.strip()) < 20 and attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                return content
            except Exception:
                # Erreur réseau ou HTTP : on réessaie, sauf à la dernière tentative
                # où l'on laisse remonter l'erreur.
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))
                else:
                    raise
        # On n'arrive ici que si toutes les tentatives ont été des 429.
        raise RuntimeError("Groq API : max retries atteint.")


# Client pour l'API OpenAI, via la bibliothèque officielle "openai".
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

        # OpenAI() lit automatiquement OPENAI_API_KEY dans l'environnement.
        client = OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
        )
        return response.choices[0].message.content
