# Crée une base SQLite locale et y charge le catalogue de questions
# et le corpus RAG, selon le schéma défini dans db/schema.sql.

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

# Dossier de sortie : variable ASSISTANT_OUTPUT_DIR si elle existe, sinon outputs/local.
# Un chemin relatif est interprété depuis la racine du dépôt.
ROOT = Path(__file__).resolve().parents[1]
_output_env = os.environ.get("ASSISTANT_OUTPUT_DIR")
OUTPUTS = Path(_output_env).expanduser() if _output_env else ROOT / "outputs" / "local"
if not OUTPUTS.is_absolute():
    OUTPUTS = ROOT / OUTPUTS
# Fichiers d'entrée et base de données produite.
DB_PATH = OUTPUTS / "assistant_eval.sqlite"
SCHEMA = ROOT / "db" / "schema.sql"
CATALOG = ROOT / "data" / "eval" / "test_catalog.jsonl"
RAG = ROOT / "data" / "rag_corpus" / "safe_synthetic_rag_corpus.jsonl"


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
# Crée les tables (le script SQL contient les CREATE TABLE).
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))

# Insère chaque question du catalogue. Les "?" sont des paramètres liés :
# sqlite3 échappe lui-même les valeurs, ce qui évite toute injection SQL.
# INSERT OR REPLACE écrase une question déjà présente avec le même id
# (le script peut donc être relancé sans créer de doublons).
# La liste des concepts est stockée sous forme de texte JSON.
    with CATALOG.open("r", encoding="utf-8") as f:
        for line in f:
            q = json.loads(line)
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_questions
                (id, domain, category, difficulty, question, reference_answer, expected_concepts_json, requires_code, trap, split)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q["id"], q["domain"], q["category"], q["difficulty"], q["question"],
                    q["reference_answer"], json.dumps(q["expected_concepts"], ensure_ascii=False),
                    int(bool(q["requires_code"])), q.get("trap", ""), q.get("split", "dev"),
                ),
            )

# Insère les documents du corpus RAG de la même façon.
    with RAG.open("r", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            conn.execute(
                """
                INSERT OR REPLACE INTO rag_documents (doc_id, title, domain, audience, text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (d["doc_id"], d["title"], d["domain"], d["audience"], d["text"]),
            )

# Valide les insertions puis ferme la connexion.
    conn.commit()
    conn.close()
    print(f"SQLite database initialized: {DB_PATH}")


if __name__ == "__main__":
    main()
