"""Adaptador da porta Snapshot sobre SQLite (o banco só deste serviço)."""

import sqlite3


class SnapshotSqlite:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        db.execute(
            "CREATE TABLE IF NOT EXISTS snapshot (chave TEXT PRIMARY KEY, tipo TEXT, hash TEXT)"
        )

    def hashes(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT chave, hash FROM snapshot"))

    def gravar(self, mudancas: dict[str, tuple[str, str | None]]) -> None:
        with self.db:  # uma transação
            for chave, (tipo, h) in mudancas.items():
                if h is None:
                    self.db.execute("DELETE FROM snapshot WHERE chave = ?", (chave,))
                else:
                    self.db.execute(
                        "INSERT OR REPLACE INTO snapshot VALUES (?, ?, ?)", (chave, tipo, h)
                    )
