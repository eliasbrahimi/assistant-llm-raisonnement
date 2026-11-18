PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS eval_questions (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    category TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    question TEXT NOT NULL,
    reference_answer TEXT NOT NULL,
    expected_concepts_json TEXT NOT NULL,
    requires_code INTEGER NOT NULL DEFAULT 0,
    trap TEXT,
    split TEXT NOT NULL DEFAULT 'dev'
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy TEXT NOT NULL,
    version TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    UNIQUE(strategy, version)
);

CREATE TABLE IF NOT EXISTS model_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    temperature REAL NOT NULL DEFAULT 0.2,
    max_output_tokens INTEGER,
    config_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_name TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    split TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    strategy TEXT NOT NULL,
    prompt_version TEXT,
    model_config_id INTEGER,
    response_text TEXT NOT NULL,
    latency_ms INTEGER,
    valid_format INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(run_id) REFERENCES eval_runs(id),
    FOREIGN KEY(question_id) REFERENCES eval_questions(id),
    FOREIGN KEY(model_config_id) REFERENCES model_configs(id)
);

CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id INTEGER NOT NULL,
    correctness REAL NOT NULL,
    structure REAL NOT NULL,
    pedagogy REAL NOT NULL,
    verification REAL NOT NULL,
    safety_limits REAL NOT NULL,
    overall REAL NOT NULL,
    grader TEXT NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(answer_id) REFERENCES answers(id)
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    answer_id INTEGER,
    question_id TEXT,
    strategy TEXT,
    severity TEXT NOT NULL,
    error_type TEXT NOT NULL,
    observed_issue TEXT NOT NULL,
    root_cause_hypothesis TEXT,
    remediation TEXT,
    retest_status TEXT DEFAULT 'todo',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(answer_id) REFERENCES answers(id),
    FOREIGN KEY(question_id) REFERENCES eval_questions(id)
);

CREATE TABLE IF NOT EXISTS rag_documents (
    doc_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    domain TEXT NOT NULL,
    audience TEXT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);