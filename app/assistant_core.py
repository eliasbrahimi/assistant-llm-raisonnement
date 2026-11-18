from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List

REQUIRED_SECTIONS = [
    "reformulation",
    "raisonnement structuré",
    "exemple",
    "limites et vérification",
]

JSON_REQUIRED_KEYS = ["reformulation", "reasoning_steps", "example", "verification", "limitations"]


@dataclass
class ValidationResult:
    valid: bool
    missing_sections: List[str]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


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
    json_match = re.search(r'\{[\s\S]*"reformulation"[\s\S]*\}', stripped)
    if json_match:
        return json_match.group(0)
    return None


def _validate_json_response(text: str) -> ValidationResult:
    """Validate that text contains valid JSON with all required keys non-empty."""
    json_text = _extract_json_text(text)
    if json_text is None:
        return ValidationResult(valid=False, missing_sections=list(JSON_REQUIRED_KEYS))

    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return ValidationResult(valid=False, missing_sections=list(JSON_REQUIRED_KEYS))

    missing = []
    for key in JSON_REQUIRED_KEYS:
        if key not in data:
            missing.append(key)
        elif key == "reasoning_steps":
            val = data[key]
            if not isinstance(val, list) or len(val) == 0:
                missing.append(key)
        elif not str(data.get(key, "")).strip():
            missing.append(key)

    return ValidationResult(valid=len(missing) == 0, missing_sections=missing)


def validate_four_block_response(text: str) -> ValidationResult:
    # Try JSON validation first
    if _extract_json_text(text) is not None:
        return _validate_json_response(text)
    # Fall back to text section validation
    return _validate_four_block_response_impl(text)


def _validate_four_block_response_impl(text: str) -> ValidationResult:
    lines = text.splitlines()
    normalized_headings = []
    for line in lines:
        heading = normalize(line)
        heading = re.sub(r"^\d+\.\s*", "", heading).removesuffix(":").strip()
        normalized_headings.append(heading)

    positions = []
    missing = []
    for required_section in REQUIRED_SECTIONS:
        try:
            positions.append(normalized_headings.index(required_section))
        except ValueError:
            missing.append(required_section)
    if missing:
        return ValidationResult(valid=False, missing_sections=missing)

    if positions != sorted(positions):
        return ValidationResult(valid=False, missing_sections=["ordre des sections"])

    empty_sections = []
    for index, section in enumerate(REQUIRED_SECTIONS):
        start = positions[index] + 1
        end = positions[index + 1] if index + 1 < len(positions) else len(lines)
        content = "\n".join(lines[start:end]).strip()
        if len(content) < 2:
            empty_sections.append(section)

    return ValidationResult(valid=not empty_sections, missing_sections=empty_sections)


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
            pass
    return text


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


def concept_coverage(text: str, expected_concepts: List[str]) -> float:
    if not expected_concepts:
        return 1.0
    norm = normalize(text)
    hits = sum(1 for concept in expected_concepts if _concept_hit(norm, concept))
    return hits / len(expected_concepts)


def weighted_score(scores: Dict[str, float]) -> float:
    return round(
        0.40 * scores["correctness"]
        + 0.20 * scores["structure"]
        + 0.20 * scores["pedagogy"]
        + 0.15 * scores["verification"]
        + 0.05 * scores["safety_limits"],
        3,
    )


def heuristic_score(text: str, expected_concepts: List[str], requires_code: bool) -> Dict[str, float]:
    validation = validate_four_block_response(text)
    full_text = _extract_full_text(text)
    coverage = concept_coverage(full_text, expected_concepts)
    norm = normalize(full_text)

    correctness = min(3.0, round(coverage * 3, 2))
    structure = 3.0 if validation.valid else max(0.0, 3.0 - len(validation.missing_sections))
    pedagogy = 3.0 if len(full_text) > 150 and any(
        word in norm for word in [
            "exemple", "example", "vérifier", "tester", "etudiant", "debutant",
            "verification", "erreur", "attention", "important", "comprendre",
            "etape", "resultat", "afficher", "executer", "sortie", "retour",
        ]
    ) else 2.0
    verification = 3.0 if any(
        word in norm for word in ["vérifier", "test", "exécuter", "assert", "comparer", "verification", "tester"]
    ) else 0.0
    code_ok = ("```" in text or "def " in full_text or "print(" in full_text) if requires_code else True
    if requires_code and not code_ok:
        pedagogy = max(0.0, pedagogy - 1.0)
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
