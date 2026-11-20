# Smoke test : vérification rapide que le dépôt fonctionne de bout en bout.
# C'est ce script que lance la CI GitHub Actions (.github/workflows/smoke.yml).
# Lancement : make smoke

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Dossiers dont on vérifie la syntaxe (ceux qui n'existent pas sont ignorés).
PYTHON_DIRS = ("app", "scripts", "tests", "grpo_bonus", "pyrit", "promptfoo")


# Trois étapes : 1) syntaxe, 2) tests unitaires, 3) évaluation complète
# dans un dossier temporaire (supprimé automatiquement à la fin).
def main() -> None:
    compile_python_sources()
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])

    with tempfile.TemporaryDirectory(prefix="assistant-eval-") as output_dir:
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["ASSISTANT_OUTPUT_DIR"] = output_dir
        run([sys.executable, "scripts/run_before_after_eval.py"], env=env)
        assert_eval_outputs(Path(output_dir))

    print("Smoke OK: syntax, tests, deterministic evaluation, output export.", flush=True)


# Compile chaque fichier .py sans l'exécuter, pour détecter les erreurs de syntaxe.
# Toutes les erreurs sont listées avant d'arrêter avec le code de sortie 1.
def compile_python_sources() -> None:
    failures: list[str] = []
    for directory in PYTHON_DIRS:
        root = ROOT / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, str(path.relative_to(ROOT)), "exec")
            except SyntaxError as exc:
                failures.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        raise SystemExit(1)


# Lance une commande dans un sous-processus depuis la racine du dépôt.
# check=True : si la commande échoue, une exception arrête le smoke test.
def run(command: list[str], env: dict[str, str] | None = None) -> None:
    merged_env = os.environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)

    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=merged_env, check=True)


# Vérifie que l'évaluation a bien produit ses 3 fichiers.
def assert_eval_outputs(output_dir: Path) -> None:
    required = [
        "before_after_eval_results.csv",
        "before_after_eval_report.md",
        "metadata.json",
    ]
    missing = [name for name in required if not (output_dir / name).exists()]
    if missing:
        raise SystemExit(f"Missing evaluation outputs: {', '.join(missing)}")


if __name__ == "__main__":
    main()
