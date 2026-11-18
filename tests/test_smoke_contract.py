from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.assistant_core import heuristic_score, validate_four_block_response
from app.toy_target import answer


class SmokeContractTest(unittest.TestCase):
    def test_required_student_files_exist(self) -> None:
        required = [
            "README.md",
            "SAFETY.md",
            "LICENSE",
            "Makefile",
            ".gitignore",
            ".env.example",
            "requirements.txt",
            ".github/workflows/smoke.yml",
            "data/eval/test_catalog.jsonl",
            "data/eval/test_catalog.csv",
            "data/eval/rubric.csv",
            "data/rag_corpus/safe_synthetic_rag_corpus.jsonl",
            "scripts/run_before_after_eval.py",
            "scripts/smoke_repo.py",
            "app/toy_target.py",
            "app/assistant_core.py",
            "app/prompts.py",
            "notebooks/s7_defense.ipynb",
            "results/eval_report.md",
            "outputs/README.md",
            "outputs/local/.gitkeep",
        ]
        missing = [path for path in required if not (ROOT / path).exists()]
        self.assertEqual(missing, [])

    def test_no_root_office_exports_in_student_repo(self) -> None:
        office_exports = sorted(
            path.name
            for path in ROOT.iterdir()
            if path.is_file() and path.suffix.lower() in {".docx", ".xlsx"}
        )
        self.assertEqual(office_exports, [])

    def test_catalog_jsonl_contract(self) -> None:
        rows = _load_jsonl(ROOT / "data" / "eval" / "test_catalog.jsonl")
        self.assertGreaterEqual(len(rows), 30)

        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(sum(1 for row in rows if row.get("split") == "test"), 5)

        required = {
            "id",
            "domain",
            "category",
            "difficulty",
            "question",
            "reference_answer",
            "expected_concepts",
            "requires_code",
            "trap",
            "split",
        }
        for row in rows:
            self.assertTrue(required.issubset(row.keys()), row.get("id"))
            self.assertIsInstance(row["expected_concepts"], list, row["id"])
            self.assertIsInstance(row["requires_code"], bool, row["id"])
            self.assertTrue(row["question"].strip(), row["id"])

    def test_catalog_csv_matches_jsonl_ids(self) -> None:
        jsonl_ids = {row["id"] for row in _load_jsonl(ROOT / "data" / "eval" / "test_catalog.jsonl")}
        with (ROOT / "data" / "eval" / "test_catalog.csv").open(encoding="utf-8", newline="") as f:
            csv_ids = {row["id"] for row in csv.DictReader(f)}
        self.assertEqual(csv_ids, jsonl_ids)

    def test_toy_target_strategy_ordering(self) -> None:
        rows = _load_jsonl(ROOT / "data" / "eval" / "test_catalog.jsonl")
        averages: dict[str, float] = {}
        for strategy in ("baseline", "structured", "fewshot"):
            scores = []
            for case in rows:
                response = answer(case, strategy=strategy)
                score = heuristic_score(response, case["expected_concepts"], case["requires_code"])
                scores.append(score["overall"])
            averages[strategy] = sum(scores) / len(scores)

        self.assertLess(averages["baseline"], averages["structured"])
        self.assertGreaterEqual(averages["fewshot"], averages["structured"])

    def test_toy_target_does_not_read_answer_key(self) -> None:
        case = _load_jsonl(ROOT / "data" / "eval" / "test_catalog.jsonl")[0]
        poisoned = dict(case)
        poisoned["reference_answer"] = "POISON_REFERENCE_SHOULD_NOT_APPEAR"
        poisoned["expected_concepts"] = ["POISON_CONCEPT_SHOULD_NOT_APPEAR"]

        response = answer(poisoned, strategy="structured")

        self.assertNotIn("POISON_REFERENCE_SHOULD_NOT_APPEAR", response)
        self.assertNotIn("POISON_CONCEPT_SHOULD_NOT_APPEAR", response)

    def test_structured_response_contract(self) -> None:
        case = _load_jsonl(ROOT / "data" / "eval" / "test_catalog.jsonl")[0]
        response = answer(case, strategy="structured")
        validation = validate_four_block_response(response)
        self.assertTrue(validation.valid)
        payload = json.loads(response)
        for field in ("reformulation", "reasoning_steps", "example", "verification", "limitations"):
            self.assertIn(field, payload)

    def test_four_block_validator_rejects_loose_substrings(self) -> None:
        invalid = "Reformulation, exemple, raisonnement structuré, limites et vérification."
        validation = validate_four_block_response(invalid)
        self.assertFalse(validation.valid)

    def test_schema_loads_in_memory(self) -> None:
        schema = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(":memory:") as con:
            con.executescript(schema)
            tables = {
                row[0]
                for row in con.execute("select name from sqlite_master where type = 'table'")
            }
        self.assertIn("eval_questions", tables)
        self.assertIn("answers", tables)
        self.assertIn("scores", tables)

    def test_no_generated_outputs_at_top_level(self) -> None:
        top_level = [
            path.name
            for path in (ROOT / "outputs").iterdir()
            if path.is_file() and path.suffix in {".csv", ".md", ".sqlite"}
        ]
        self.assertEqual(top_level, ["README.md"])

    def test_runner_cli_writes_to_requested_output_dir(self) -> None:
        with _temporary_output_dir() as output_dir:
            env = os.environ.copy()
            env.update({"ASSISTANT_OUTPUT_DIR": str(output_dir), "PYTHONDONTWRITEBYTECODE": "1"})
            subprocess.run(
                [sys.executable, "scripts/run_before_after_eval.py"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue((output_dir / "before_after_eval_results.csv").exists())
            self.assertTrue((output_dir / "before_after_eval_report.md").exists())
            self.assertTrue((output_dir / "metadata.json").exists())


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class _temporary_output_dir:
    def __enter__(self) -> Path:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory(prefix="assistant-smoke-")
        return Path(self._tmp.name)

    def __exit__(self, *args: object) -> None:
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
