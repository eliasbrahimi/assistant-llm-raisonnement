# Cœur de l'assistant : vérifie la structure des réponses du LLM
# et leur attribue un score heuristique (sans appel à un modèle juge).

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List

# Les 4 sections attendues dans une réponse au format texte, dans cet ordre.
REQUIRED_SECTIONS = [
    "reformulation",
    "raisonnement structuré",
    "exemple",
    "limites et vérification",
]

# Les clés obligatoires quand le modèle répond en JSON (prompts "structured" et "fewshot").
JSON_REQUIRED_KEYS = ["reformulation", "reasoning_steps", "example", "verification", "limitations"]


# Résultat d'une validation : la réponse est-elle conforme, et sinon ce qui manque.
@dataclass
class ValidationResult:
    valid: bool
    missing_sections: List[str]


# Met le texte en minuscules et remplace toute suite d'espaces/retours à la ligne
# par un seul espace, pour comparer des chaînes sans se soucier de la mise en forme.
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


# Cherche un objet JSON dans la réponse du modèle, qui peut être :
# du JSON brut, du JSON dans un bloc ```json ... ```, ou du JSON noyé dans du texte.
# Renvoie None si aucun JSON n'est trouvé.
def _extract_json_text(text: str) -> str | None:
    """Try to extract a JSON object string from text."""
    stripped = text.strip()
    # Already a JSON object — return as-is (inner code blocks are just string values)
    if stripped.startswith("{"):
        return stripped
    # Strip outer markdown code block wrapping a JSON object
    code_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", stripped)
    if code_match:
        return code_match.group(1).strip()
    # JSON object embedded in surrounding text
    # (on exige la clé "reformulation" pour ne pas capturer n'importe quelle accolade)
    json_match = re.search(r'\{[\s\S]*"reformulation"[\s\S]*\}', stripped)
    if json_match:
        return json_match.group(0)
    return None


# Valide une réponse JSON : elle doit se parser et contenir les 5 clés, toutes non vides.
def _validate_json_response(text: str) -> ValidationResult:
    """Validate that text contains valid JSON with all required keys non-empty."""
    json_text = _extract_json_text(text)
    if json_text is None:
        # Pas de JSON du tout : toutes les clés sont considérées manquantes.
        return ValidationResult(valid=False, missing_sections=list(JSON_REQUIRED_KEYS))

    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        # JSON mal formé (virgule en trop, guillemets manquants...) : même sanction.
        return ValidationResult(valid=False, missing_sections=list(JSON_REQUIRED_KEYS))

    missing = []
    for key in JSON_REQUIRED_KEYS:
        if key not in data:
            missing.append(key)
        elif key == "reasoning_steps":
            # Les étapes de raisonnement doivent être une liste non vide.
            val = data[key]
            if not isinstance(val, list) or len(val) == 0:
                missing.append(key)
        elif not str(data.get(key, "")).strip():
            # Les autres clés doivent contenir du texte (pas seulement des espaces).
            missing.append(key)

    return ValidationResult(valid=len(missing) == 0, missing_sections=missing)


# Point d'entrée de la validation : accepte les deux formats de réponse.
def validate_four_block_response(text: str) -> ValidationResult:
    # Try JSON validation first
    if _extract_json_text(text) is not None:
        return _validate_json_response(text)
    # Fall back to text section validation
    return _validate_four_block_response_impl(text)


# Valide une réponse au format texte : les 4 titres doivent être présents,
# dans le bon ordre, et chaque section doit avoir un contenu.
def _validate_four_block_response_impl(text: str) -> ValidationResult:
    lines = text.splitlines()
    # On normalise chaque ligne pour reconnaître les titres même écrits
    # "1. Reformulation :" ou "REFORMULATION" : on retire la numérotation et le ":" final.
    normalized_headings = []
    for line in lines:
        heading = normalize(line)
        heading = re.sub(r"^\d+\.\s*", "", heading).removesuffix(":").strip()
        normalized_headings.append(heading)

    # Repère la ligne de chaque titre attendu (première occurrence).
    positions = []
    missing = []
    for required_section in REQUIRED_SECTIONS:
        try:
            positions.append(normalized_headings.index(required_section))
        except ValueError:
            missing.append(required_section)
    if missing:
        return ValidationResult(valid=False, missing_sections=missing)

    # Les titres doivent apparaître dans l'ordre de REQUIRED_SECTIONS.
    if positions != sorted(positions):
        return ValidationResult(valid=False, missing_sections=["ordre des sections"])

    # Le contenu d'une section va de la ligne après son titre jusqu'au titre suivant
    # (ou la fin du texte pour la dernière). Moins de 2 caractères = section vide.
    empty_sections = []
    for index, section in enumerate(REQUIRED_SECTIONS):
        start = positions[index] + 1
        end = positions[index + 1] if index + 1 < len(positions) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        if len(content) < 2:
            empty_sections.append(section)

    return ValidationResult(valid=not empty_sections, missing_sections=empty_sections)


# Rassemble tout le texte utile d'une réponse. Pour du JSON, on concatène les valeurs
# des clés (sans les noms de clés) afin que la recherche de concepts porte sur le contenu.
def _extract_full_text(text: str) -> str:
    """Return all textual content from a response (JSON or plain text)."""
    json_text = _extract_json_text(text)
    if json_text is not None:
        try:
            data = json.loads(json_text)
            parts = []
            for key in JSON_REQUIRED_KEYS:
                val = data.get(key, "")
                if isinstance(val, list):
                    parts.extend(str(v) for v in val)
                else:
                    parts.append(str(val))
            return " ".join(parts)
        except (json.JSONDecodeError, ValueError):
            # JSON illisible : on retombe sur le texte brut.
            pass
    return text


# Indique si un concept attendu (ex. "cas de base") est couvert par la réponse.
# Attention : la règle 3 est permissive, un seul mot long suffit à valider le concept,
# ce qui peut surestimer le score de justesse.
def _concept_hit(norm_text: str, concept: str) -> bool:
    """True if the concept is covered in the text.

    Strategy (in order):
    1. Exact phrase match after normalisation.
    2. All significant words (>= 3 chars) of the concept appear individually.
    3. Any single significant word (>= 4 chars) appears — partial credit.
    """
    nc = normalize(concept)
    if nc in norm_text:
        return True
    words = [w for w in re.split(r"\s+", nc) if len(w) >= 3]
    if not words:
        return False
    # All significant words present individually
    if all(w in norm_text for w in words):
        return True
    # At least one long word (>= 4 chars) present
    long_words = [w for w in words if len(w) >= 4]
    if long_words and any(w in norm_text for w in long_words):
        return True
    return False


# Proportion des concepts attendus trouvés dans la réponse (entre 0 et 1).
# Sans concept attendu, la couverture vaut 1 par convention.
def concept_coverage(text: str, expected_concepts: List[str]) -> float:
    if not expected_concepts:
        return 1.0
    norm = normalize(text)
    hits = sum(1 for concept in expected_concepts if _concept_hit(norm, concept))
    return hits / len(expected_concepts)


# Score global = moyenne pondérée des 5 critères (chacun noté de 0 à 3).
# La justesse pèse le plus (40 %), la sécurité/limites le moins (5 %).
def weighted_score(scores: Dict[str, float]) -> float:
    return round(
        0.40 * scores["correctness"]
        + 0.20 * scores["structure"]
        + 0.20 * scores["pedagogy"]
        + 0.15 * scores["verification"]
        + 0.05 * scores["safety_limits"],
        3,
    )


# Note une réponse sur les 5 critères de la grille (data/eval/rubric.csv),
# avec des règles simples à base de mots-clés, puis calcule le score global.
def heuristic_score(text: str, expected_concepts: List[str], requires_code: bool) -> Dict[str, float]:
    validation = validate_four_block_response(text)
    full_text = _extract_full_text(text)
    coverage = concept_coverage(full_text, expected_concepts)
    norm = normalize(full_text)

    # Justesse : couverture des concepts ramenée sur 3.
    correctness = min(3.0, round(coverage * 3, 2))
    # Structure : 3 si conforme, sinon on retire 1 point par section manquante.
    structure = 3.0 if validation.valid else max(0.0, 3.0 - len(validation.missing_sections))
    # Pédagogie : 3 si la réponse est assez longue (> 150 caractères)
    # et contient au moins un mot "pédagogique", sinon 2.
    pedagogy = 3.0 if len(full_text) > 150 and any(
        word in norm for word in [
            "exemple", "example", "vérifier", "tester", "etudiant", "debutant",
            "verification", "erreur", "attention", "important", "comprendre",
            "etape", "resultat", "afficher", "executer", "sortie", "retour",
        ]
    ) else 2.0
    # Vérification : 3 si la réponse propose de tester/vérifier, sinon 0 (tout ou rien).
    verification = 3.0 if any(
        word in norm for word in ["vérifier", "test", "exécuter", "assert", "comparer", "verification", "tester"]
    ) else 0.0
    # Si la question demande du code, on cherche un bloc de code ou du Python reconnaissable.
    # Absence de code = 1 point de pédagogie en moins.
    code_ok = ("```" in text or "def " in full_text or "print(" in full_text) if requires_code else True
    if requires_code and not code_ok:
        pedagogy = max(0.0, pedagogy - 1.0)
    # Sécurité/limites : 3 si la réponse mentionne ses limites ou incertitudes, sinon 2.
    safety_limits = 3.0 if any(
        word in norm for word in ["limite", "ambigu", "vérification", "ne pas inventer", "limitations", "limitation"]
    ) else 2.0

    scores = {
        "correctness": correctness,
        "structure": structure,
        "pedagogy": pedagogy,
        "verification": verification,
        "safety_limits": safety_limits,
    }
    scores["overall"] = weighted_score(scores)
    return scores
