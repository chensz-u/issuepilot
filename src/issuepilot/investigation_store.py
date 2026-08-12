import json
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from issuepilot.investigation_domain import Investigation, InvestigationEvent


class InvestigationStore:
    def __init__(
        self,
        path: str | Path,
        clock: Callable[[], float] = time.time,
        lease_seconds: float = 30.0,
    ) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.path = str(path)
        self.clock = clock
        self.lease_seconds = lease_seconds
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigation_events (
                    investigation_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (investigation_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS investigation_decision_claims (
                    investigation_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(investigation_decision_claims)"
                ).fetchall()
            }
            if "owner" not in columns:
                connection.execute(
                    "ALTER TABLE investigation_decision_claims "
                    "ADD COLUMN owner TEXT NOT NULL DEFAULT ''"
                )
            if "expires_at" not in columns:
                connection.execute(
                    "ALTER TABLE investigation_decision_claims "
                    "ADD COLUMN expires_at REAL NOT NULL DEFAULT 0"
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def save(self, investigation: Investigation, decision_owner: str | None = None) -> None:
        payload = json.dumps(investigation.model_dump(mode="json"), sort_keys=True)
        with self._connect() as connection:
            if decision_owner:
                connection.execute("BEGIN IMMEDIATE")
                lease = connection.execute(
                    "SELECT 1 FROM investigation_decision_claims "
                    "WHERE investigation_id = ? AND owner = ? AND expires_at > ?",
                    (investigation.id, decision_owner, self.clock()),
                ).fetchone()
                if lease is None:
                    raise ValueError("investigation decision lease was lost")
            connection.execute(
                """
                INSERT INTO investigations (id, payload) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET payload = excluded.payload
                """,
                (investigation.id, payload),
            )

    def get(self, investigation_id: str) -> Investigation:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM investigations WHERE id = ?", (investigation_id,)
            ).fetchone()
        if row is None:
            raise KeyError(investigation_id)
        return Investigation.model_validate_json(row[0])

    def append_event(
        self, investigation_id: str, name: str, payload: dict[str, Any]
    ) -> InvestigationEvent:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) FROM investigation_events
                WHERE investigation_id = ?
                """,
                (investigation_id,),
            ).fetchone()
            sequence = int(row[0]) + 1
            connection.execute(
                "INSERT INTO investigation_events VALUES (?, ?, ?, ?)",
                (investigation_id, sequence, name, json.dumps(payload, sort_keys=True)),
            )
        return InvestigationEvent(sequence=sequence, name=name, payload=payload)

    def list_events(self, investigation_id: str) -> list[InvestigationEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sequence, name, payload FROM investigation_events
                WHERE investigation_id = ? ORDER BY sequence
                """,
                (investigation_id,),
            ).fetchall()
        return [
            InvestigationEvent(sequence=row[0], name=row[1], payload=json.loads(row[2]))
            for row in rows
        ]

    def claim_decision(self, investigation_id: str, owner: str) -> bool:
        now = self.clock()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "DELETE FROM investigation_decision_claims "
                "WHERE investigation_id = ? AND expires_at <= ?",
                (investigation_id, now),
            )
            cursor = connection.execute(
                "INSERT OR IGNORE INTO investigation_decision_claims VALUES (?, ?, ?)",
                (investigation_id, owner, now + self.lease_seconds),
            )
            return cursor.rowcount == 1

    def renew_decision(self, investigation_id: str, owner: str) -> bool:
        now = self.clock()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE investigation_decision_claims SET expires_at = ? "
                "WHERE investigation_id = ? AND owner = ? AND expires_at > ?",
                (now + self.lease_seconds, investigation_id, owner, now),
            )
            return cursor.rowcount == 1

    def release_decision(self, investigation_id: str, owner: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM investigation_decision_claims "
                "WHERE investigation_id = ? AND owner = ?",
                (investigation_id, owner),
            )
