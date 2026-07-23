"""Small persistent user-settings store.

SQLite is the safe default for local development.  Render deployments must set
``DATABASE_URL`` to a persistent PostgreSQL database; otherwise the worker
emits a clear warning rather than pretending that an ephemeral filesystem is
durable.
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


class UserStore:
    def __init__(self, database_url: str | None = None, sqlite_path: str = "telegram_state.sqlite3"):
        self.database_url = database_url or os.getenv("DATABASE_URL", "")
        # Keep the dependency surface small. psycopg is optional but PostgreSQL
        # is used when a deployment has installed it.
        if self.database_url.startswith(("postgres://", "postgresql://")):
            try:
                import psycopg  # type: ignore
            except ImportError as exc:
                raise RuntimeError("DATABASE_URL ist gesetzt, aber psycopg fehlt.") from exc
            self.kind = "postgres"; self.connection = psycopg.connect(self.database_url)
        else:
            self.kind = "sqlite"; Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            self.connection = sqlite3.connect(sqlite_path)
        self._migrate()

    def _migrate(self) -> None:
        serial = "BIGINT" if self.kind == "postgres" else "INTEGER"
        with self.connection.cursor() if self.kind == "postgres" else self.connection:
            cursor = self.connection.cursor() if self.kind == "postgres" else self.connection
            cursor.execute(f"CREATE TABLE IF NOT EXISTS telegram_watchlist (user_id {serial}, symbol TEXT, PRIMARY KEY (user_id, symbol))")
            cursor.execute(f"CREATE TABLE IF NOT EXISTS telegram_settings (user_id {serial} PRIMARY KEY, view_mode TEXT NOT NULL DEFAULT 'detailed', timezone TEXT NOT NULL DEFAULT 'Europe/Berlin')")
        if self.kind == "postgres": self.connection.commit()

    def _execute(self, sql: str, params: tuple = ()):  # DB-API placeholder compatibility
        if self.kind == "postgres": sql = sql.replace("?", "%s")
        cursor = self.connection.cursor(); cursor.execute(sql, params)
        return cursor

    def watchlist(self, user_id: int) -> tuple[str, ...]:
        return tuple(row[0] for row in self._execute("SELECT symbol FROM telegram_watchlist WHERE user_id=? ORDER BY symbol", (user_id,)).fetchall())

    def add_symbol(self, user_id: int, symbol: str) -> None:
        if self.kind == "sqlite": self._execute("INSERT OR IGNORE INTO telegram_watchlist(user_id,symbol) VALUES (?,?)", (user_id, symbol))
        else: self._execute("INSERT INTO telegram_watchlist(user_id,symbol) VALUES (?,?) ON CONFLICT DO NOTHING", (user_id, symbol))
        self.connection.commit()

    def remove_symbol(self, user_id: int, symbol: str) -> None:
        self._execute("DELETE FROM telegram_watchlist WHERE user_id=? AND symbol=?", (user_id, symbol)); self.connection.commit()

    def clear_watchlist(self, user_id: int) -> None:
        self._execute("DELETE FROM telegram_watchlist WHERE user_id=?", (user_id,)); self.connection.commit()

    def view_mode(self, user_id: int) -> str:
        row = self._execute("SELECT view_mode FROM telegram_settings WHERE user_id=?", (user_id,)).fetchone()
        return row[0] if row else "detailed"

    def set_view_mode(self, user_id: int, value: str) -> None:
        if value not in {"compact", "detailed"}: raise ValueError("Ungültige Ansicht.")
        if self.kind == "sqlite": self._execute("INSERT INTO telegram_settings(user_id,view_mode) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET view_mode=excluded.view_mode", (user_id, value))
        else: self._execute("INSERT INTO telegram_settings(user_id,view_mode) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET view_mode=EXCLUDED.view_mode", (user_id, value))
        self.connection.commit()
