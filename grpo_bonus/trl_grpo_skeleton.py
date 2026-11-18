from __future__ import annotations

import re
from typing import List

# Skeleton only. Requires installing and configuring Hugging Face TRL, datasets,
# transformers, accelerate, and a small trainable model.

REQUIRED = ["Reformulation", "Raisonnement structuré", "Exemple", "Limites et vérification"]


def format_reward(completions: List[str], **kwargs) -> List[float]:
    rewards = []
    for text in completions:
        rewards.append(1.0 if all(section.lower() in text.lower() for section in REQUIRED) else 0.0)
    return rewards


def verification_reward(completions: List[str], **kwargs) -> List[float]:
    pattern = re.compile(r"vérifier|test|exécuter|assert|comparer", re.IGNORECASE)
    return [1.0 if pattern.search(text) else 0.0 for text in completions]


def length_reward(completions: List[str], **kwargs) -> List[float]:
    rewards = []
    for text in completions:
        n = len(text.split())
        if 80 <= n <= 260:
            rewards.append(1.0)
        elif n < 40 or n > 400:
            rewards.append(-1.0)
        else:
            rewards.append(0.0)
    return rewards


def concept_reward(completions: List[str], expected_concepts: List[List[str]] | None = None, **kwargs) -> List[float]:
    if expected_concepts is None:
        return [0.0 for _ in completions]
    rewards = []
    for text, concepts in zip(completions, expected_concepts):
        if not concepts:
            rewards.append(0.0)
            continue
        lower = text.lower()
        hits = sum(1 for c in concepts if c.lower() in lower)
        rewards.append(hits / len(concepts))
    return rewards


def refusal_reward(completions: List[str], risk_labels: List[str] | None = None, **kwargs) -> List[float]:
    """Reward bounded refusals on out-of-scope or academic-integrity cases."""
    if risk_labels is None:
        return [0.0 for _ in completions]

    refusal_terms = re.compile(r"refus|ne peux pas|plan|methode|aide pédagogique|apprentissage", re.IGNORECASE)
    rewards = []
    for text, label in zip(completions, risk_labels):
        if label in {"out_of_scope", "academic_integrity", "prompt_injection"}:
            rewards.append(1.0 if refusal_terms.search(text) else -1.0)
        else:
            rewards.append(0.0)
    return rewards


# Indicative TRL usage:
# from trl import GRPOConfig, GRPOTrainer
# trainer = GRPOTrainer(
#     model="small-model-name",
#     reward_funcs=[format_reward, verification_reward, length_reward, refusal_reward],
#     args=GRPOConfig(output_dir="outputs/grpo_run", num_generations=4),
#     train_dataset=train_dataset,
# )
# trainer.train()
