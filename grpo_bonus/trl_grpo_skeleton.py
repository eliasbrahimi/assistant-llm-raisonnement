from __future__ import annotations

import re
from typing import List

# Skeleton only. Requires installing and configuring Hugging Face TRL, datasets,
# transformers, accelerate, and a small trainable model.

# Squelette des fonctions de récompense pour un entraînement GRPO (apprentissage
# par renforcement) : le modèle génère plusieurs réponses par question, chaque fonction
# leur donne une note, et le modèle est poussé vers les réponses les mieux notées.
# Chaque fonction reçoit la liste des réponses générées et renvoie une note par réponse.
#
# Sections que doit contenir une réponse au format texte.
REQUIRED = ["Reformulation", "Raisonnement structuré", "Exemple", "Limites et vérification"]


# +1 si les 4 sections sont présentes (sans vérifier leur ordre), sinon 0.
def format_reward(completions: List[str], **kwargs) -> List[float]:
    rewards = []
    for text in completions:
        rewards.append(1.0 if all(section.lower() in text.lower() for section in REQUIRED) else 0.0)
    return rewards


# +1 si la réponse propose de vérifier ou tester, sinon 0.
def verification_reward(completions: List[str], **kwargs) -> List[float]:
    pattern = re.compile(r"vérifier|test|exécuter|assert|comparer", re.IGNORECASE)
    return [1.0 if pattern.search(text) else 0.0 for text in completions]


# Récompense une longueur raisonnable (en mots) : +1 entre 80 et 260,
# -1 si trop courte (< 40) ou trop longue (> 400), 0 entre les deux.
# Évite que le modèle apprenne à gonfler ses réponses pour gagner des points.
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


# Proportion des concepts attendus présents dans la réponse (entre 0 et 1).
# expected_concepts contient une liste de concepts par réponse.
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


# Pour les questions à risque (hors sujet, triche, injection de prompt) :
# +1 si la réponse refuse ou recadre vers une aide pédagogique, -1 sinon.
# Les autres questions ne sont pas concernées (0).
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
