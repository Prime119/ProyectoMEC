"""
Capa 4 — Memoria del asistente MEC.

Versión simplificada de la memoria de Astra:
- Corto plazo: clave/valor (preferencias del operador, última acción)
- Episódica: registro de eventos importantes del motor (anomalías, intervenciones)

Todo se almacena en SQLite junto al proyecto.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Memory:
    db_path: Path
    _db: sqlite3.Connection | None = None

    @classmethod
    def create(cls, base_dir: Path) -> "Memory":
        db_path = base_dir / "mec_memory.db"
        return cls(db_path=db_path)

    def connect(self) -> sqlite3.Connection:
        if self._db is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(self.db_path))
            self._init_schema()
        return self._db

    def _init_schema(self) -> None:
        assert self._db is not None
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS short_term (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                severity TEXT,
                content TEXT,
                motor_data TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT,
                content TEXT,
                created_at TEXT
            );
        """)
        self._db.commit()

    # --- Corto plazo (clave/valor) ---
    def remember(self, key: str, value: object) -> None:
        db = self.connect()
        db.execute(
            "INSERT INTO short_term(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), _now()),
        )
        db.commit()

    def recall(self, key: str, default: object = None) -> object:
        db = self.connect()
        row = db.execute("SELECT value FROM short_term WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    # --- Eventos del motor ---
    def log_event(self, category: str, content: str, severity: str = "info",
                  motor_data: dict | None = None) -> None:
        db = self.connect()
        db.execute(
            "INSERT INTO events(category, severity, content, motor_data, created_at) VALUES(?,?,?,?,?)",
            (category, severity, content,
             json.dumps(motor_data, ensure_ascii=False) if motor_data else None,
             _now()),
        )
        db.commit()

    def get_recent_events(self, limit: int = 20, category: str | None = None) -> list[dict]:
        db = self.connect()
        if category:
            rows = db.execute(
                "SELECT category, severity, content, created_at FROM events "
                "WHERE category=? ORDER BY id DESC LIMIT ?",
                (category, limit)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT category, severity, content, created_at FROM events "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"category": r[0], "severity": r[1], "content": r[2], "created_at": r[3]}
            for r in rows
        ]

    # --- Historial de conversación (persistente) ---
    def log_conversation(self, role: str, content: str) -> None:
        db = self.connect()
        db.execute(
            "INSERT INTO conversations(role, content, created_at) VALUES(?,?,?)",
            (role, content, _now()),
        )
        db.commit()

    def get_recent_conversations(self, limit: int = 20) -> list[dict]:
        db = self.connect()
        rows = db.execute(
            "SELECT role, content, created_at FROM conversations "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in reversed(rows)]

    # --- Reset ---
    def reset(self) -> None:
        """Reinicio limpio: olvida todo."""
        if self._db is not None:
            self._db.close()
            self._db = None
        if self.db_path.exists():
            self.db_path.unlink()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
