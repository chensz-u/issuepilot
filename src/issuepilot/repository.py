import json
import sqlite3
from pathlib import Path

from issuepilot.domain import KnowledgeDocument
from issuepilot.trace import WorkflowTrace


class SQLiteRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS traces (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                """
            )

    def upsert_documents(self, documents: list[KnowledgeDocument]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO documents (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                [(document.id, document.model_dump_json()) for document in documents],
            )

    def list_documents(self) -> list[KnowledgeDocument]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM documents ORDER BY id").fetchall()
        return [KnowledgeDocument.model_validate_json(row["payload"]) for row in rows]

    def save(self, trace: WorkflowTrace) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO traces (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (trace.id, json.dumps(trace.model_dump(), sort_keys=True)),
            )

    def get(self, trace_id: str) -> WorkflowTrace:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM traces WHERE id = ?", (trace_id,)
            ).fetchone()
        if row is None:
            raise KeyError(trace_id)
        return WorkflowTrace.model_validate_json(row["payload"])
