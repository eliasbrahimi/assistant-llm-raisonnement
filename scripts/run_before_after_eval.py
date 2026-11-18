from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import toy_target
from app.assistant_core import heuristic_score, validate_four_block_response
from app.prompts import PROMPTS

CATALOG = ROOT / "data" / "eval" / "test_catalog.jsonl"
_output_env = os.environ.get("ASSISTANT_OUTPUT_DIR")
OUTPUTS = Path(_output_env).expanduser() if _output_env else ROOT / "outputs" / "local"
if not OUTPUTS.is_absolute():
    OUTPUTS = ROOT / OUTPUTS

STRATEGIES = ["baseline", "structured", "fewshot"]


def load_cases():
    with CATALOG.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _make_answerer(strategy: str):
    """Return a callable(case) -> str.

    Uses the real Groq API when GROQ_API_KEY is set, otherwise falls back
    to the deterministic toy target for smoke testing.
    """
    if os.environ.get("GROQ_API_KEY"):
        from app.model_clients import GroqModelClient
        client = GroqModelClient(strategy=strategy)
        prompt_template = PROMPTS[strategy]

        def _groq_answer(case: dict) -> str:
            prompt = prompt_template.replace("{question}", case["question"])
            time.sleep(1)  # respect Groq rate limit
            return client.generate(prompt, case=case)

        return _groq_answer

    return lambda case: toy_target.answer(case, strategy=strategy)


def run_strategy(cases, strategy: str):
    answerer = _make_answerer(strategy)
    rows = []
    for case in cases:
        start = time.perf_counter()
        response = answerer(case)
        latency_ms = int((time.perf_counter() - start) * 1000)
        validation = validate_four_block_response(response)
        score = heuristic_score(response, case.get("expected_concepts", []), bool(case.get("requires_code", False)))
        rows.append({
            "run_timestamp": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "question_id": case["id"],
            "split": case.get("split", "dev"),
            "category": case["category"],
            "difficulty": case["difficulty"],
            "strategy": strategy,
            "valid_format": int(validation.valid),
            "missing_sections": ";".join(validation.missing_sections),
            "latency_ms": latency_ms,
            **score,
            "question": case["question"],
            "response_text": response.replace("\n", "\\n"),
        })
    return rows


def write_csv(path: Path, rows):
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows):
    by_strategy = {}
    for row in rows:
        s = row["strategy"]
        by_strategy.setdefault(s, []).append(row)
    lines = ["# Rapport automatique avant/après", ""]
    using_api = bool(os.environ.get("GROQ_API_KEY"))
    target_label = "API Groq (llama-3.3-70b-versatile)" if using_api else "cible déterministe locale (toy target)"
    lines.append(f"> Cible utilisée : {target_label}")
    lines.append("")
    lines.append("| Stratégie | N | Score moyen | Format valide | Vérification moyenne |")
    lines.append("|---|---:|---:|---:|---:|")
    for strategy, items in sorted(by_strategy.items()):
        n = len(items)
        avg = sum(float(x["overall"]) for x in items) / n
        fmt = sum(int(x["valid_format"]) for x in items) / n
        ver = sum(float(x["verification"]) for x in items) / n
        lines.append(f"| {strategy} | {n} | {avg:.2f} | {fmt:.2%} | {ver:.2f} |")
    lines.append("")

    lines.append("## Lecture par split")
    lines.append("")
    lines.append("| Split | Stratégie | N | Score moyen |")
    lines.append("|---|---|---:|---:|")
    split_keys = sorted({(row["split"], row["strategy"]) for row in rows})
    for split, strategy in split_keys:
        items = [row for row in rows if row["split"] == split and row["strategy"] == strategy]
        avg = sum(float(x["overall"]) for x in items) / len(items)
        lines.append(f"| {split} | {strategy} | {len(items)} | {avg:.2f} |")
    lines.append("")

    lines.append("## Utilisation attendue")
    lines.append("")
    lines.append("1. Lancer sans GROQ_API_KEY pour tester le pipeline (toy target).")
    lines.append("2. Lancer avec GROQ_API_KEY pour une évaluation réelle du modèle.")
    lines.append("3. Conserver exactement le même catalogue de questions.")
    lines.append("4. Comparer baseline, prompt structuré et few-shot.")
    lines.append("5. Documenter les erreurs dans le findings register.")
    return "\n".join(lines)


def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    all_rows = []
    for strategy in STRATEGIES:
        print(f"Running strategy: {strategy} ...")
        all_rows.extend(run_strategy(cases, strategy))
    out_csv = OUTPUTS / "before_after_eval_results.csv"
    write_csv(out_csv, all_rows)
    report = summarize(all_rows)
    (OUTPUTS / "before_after_eval_report.md").write_text(report, encoding="utf-8")
    metadata = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "catalog": str(CATALOG.relative_to(ROOT)),
        "question_count": len(cases),
        "strategies": STRATEGIES,
        "target": "groq api" if os.environ.get("GROQ_API_KEY") else "toy target (deterministic)",
    }
    (OUTPUTS / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_csv}")
    print(f"Wrote {OUTPUTS / 'before_after_eval_report.md'}")
    print(f"Wrote {OUTPUTS / 'metadata.json'}")


if __name__ == "__main__":
    main()
