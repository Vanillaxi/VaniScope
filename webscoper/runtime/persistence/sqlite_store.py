from __future__ import annotations

import json
import os
import sqlite3
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "data/vaniscope.db"
DEFAULT_RUNTIME_LOCAL_CONFIG_PATH = PROJECT_ROOT / "configs/runtime.local.toml"


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    title: str
    created_at: str
    updated_at: str
    last_task_id: str | None = None
    metadata_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class MessageRecord:
    id: str
    conversation_id: str
    role: str
    content: str
    task_id: str | None
    metadata_json: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class TaskMetadataRecord:
    id: str
    conversation_id: str | None
    status: str
    task_type: str
    skill_id: str | None
    input_json: dict[str, Any]
    run_dir: str | None
    error: str | None
    error_type: str | None
    created_at: str
    updated_at: str


class SQLitePersistenceStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else resolve_default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_conversation(
        self,
        *,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationRecord:
        now = _utc_now()
        conversation_id = _new_id("conv")
        display_title = (title or "New conversation").strip() or "New conversation"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversations (
                    id, title, created_at, updated_at, last_task_id, metadata_json
                ) VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (
                    conversation_id,
                    display_title,
                    now,
                    now,
                    _json_dumps(metadata or {}),
                ),
            )
        return ConversationRecord(
            id=conversation_id,
            title=display_title,
            created_at=now,
            updated_at=now,
            metadata_json=metadata or {},
        )

    def list_conversations(self, limit: int = 50) -> list[ConversationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, created_at, updated_at, last_task_id, metadata_json
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, title, created_at, updated_at, last_task_id, metadata_json
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return _conversation_from_row(row) if row is not None else None

    def add_message(
        self,
        *,
        conversation_id: str,
        role: str,
        content: str,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        if self.get_conversation(conversation_id) is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        now = _utc_now()
        message_id = _new_id("msg")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages (
                    id, conversation_id, role, content, task_id, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    conversation_id,
                    role,
                    content,
                    task_id,
                    _json_dumps(metadata or {}),
                    now,
                ),
            )
            conn.execute(
                "UPDATE conversations SET updated_at = ?, last_task_id = COALESCE(?, last_task_id) WHERE id = ?",
                (now, task_id, conversation_id),
            )
        return MessageRecord(
            id=message_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            task_id=task_id,
            metadata_json=metadata or {},
            created_at=now,
        )

    def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, conversation_id, role, content, task_id, metadata_json, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [_message_from_row(row) for row in rows]

    def upsert_task(
        self,
        *,
        task_id: str,
        conversation_id: str | None,
        status: str,
        task_type: str,
        skill_id: str | None,
        input_json: dict[str, Any],
        run_dir: str | None,
        error: str | None = None,
        error_type: str | None = None,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT created_at FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            conn.execute(
                """
                INSERT INTO tasks (
                    id, conversation_id, status, task_type, skill_id, input_json,
                    run_dir, error, error_type, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    conversation_id = excluded.conversation_id,
                    status = excluded.status,
                    task_type = excluded.task_type,
                    skill_id = excluded.skill_id,
                    input_json = excluded.input_json,
                    run_dir = excluded.run_dir,
                    error = excluded.error,
                    error_type = excluded.error_type,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    conversation_id,
                    status,
                    task_type,
                    skill_id,
                    _json_dumps(input_json),
                    run_dir,
                    error,
                    error_type,
                    created_at,
                    now,
                ),
            )
            if conversation_id:
                conn.execute(
                    "UPDATE conversations SET updated_at = ?, last_task_id = ? WHERE id = ?",
                    (now, task_id, conversation_id),
                )

    def get_task(self, task_id: str) -> TaskMetadataRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, conversation_id, status, task_type, skill_id, input_json,
                       run_dir, error, error_type, created_at, updated_at
                FROM tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return _task_from_row(row) if row is not None else None

    def upsert_artifact(
        self,
        *,
        task_id: str,
        name: str,
        kind: str,
        path: str,
        size: int | None,
    ) -> None:
        now = _utc_now()
        artifact_id = f"{task_id}:{name}"
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (id, task_id, name, kind, path, size, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind = excluded.kind,
                    path = excluded.path,
                    size = excluded.size
                """,
                (artifact_id, task_id, name, kind, path, size, now),
            )

    def upsert_approval(
        self,
        *,
        approval_id: str,
        task_id: str,
        status: str,
        risk_level: str,
        reason: str,
        decision: dict[str, Any] | None,
        created_at: str | None,
        decided_at: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals (
                    id, task_id, status, risk_level, reason, decision,
                    created_at, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    risk_level = excluded.risk_level,
                    reason = excluded.reason,
                    decision = excluded.decision,
                    decided_at = excluded.decided_at
                """,
                (
                    approval_id,
                    task_id,
                    status,
                    risk_level,
                    reason,
                    _json_dumps(decision or {}),
                    created_at or _utc_now(),
                    decided_at,
                ),
            )

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_task_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    task_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT REFERENCES conversations(id),
                    status TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    skill_id TEXT,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    run_dir TEXT,
                    error TEXT,
                    error_type TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    status TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    decision TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_conversation
                    ON tasks(conversation_id, updated_at);
                CREATE INDEX IF NOT EXISTS idx_artifacts_task
                    ON artifacts(task_id);
                CREATE INDEX IF NOT EXISTS idx_approvals_task
                    ON approvals(task_id);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


ConversationStore = SQLitePersistenceStore


def resolve_default_db_path(
    *,
    runtime_config_path: str | Path | None = None,
    fallback_runs_dir: Path | None = None,
) -> Path:
    env_path = os.getenv("VANISCOPE_DB_PATH")
    if env_path:
        return Path(env_path)

    config_path = (
        Path(runtime_config_path)
        if runtime_config_path is not None
        else DEFAULT_RUNTIME_LOCAL_CONFIG_PATH
    )
    if config_path.exists():
        configured = _read_configured_db_path(config_path)
        if configured:
            return configured

    if fallback_runs_dir is not None and fallback_runs_dir != Path("runs"):
        return fallback_runs_dir.parent / "vaniscope.db"
    return DEFAULT_DB_PATH


def _read_configured_db_path(path: Path) -> Path | None:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None
    persistence = payload.get("persistence")
    if not isinstance(persistence, dict):
        return None
    value = persistence.get("sqlite_path") or persistence.get("db_path")
    if not isinstance(value, str) or not value.strip():
        return None
    configured = Path(value)
    return configured if configured.is_absolute() else PROJECT_ROOT / configured


def _conversation_from_row(row: sqlite3.Row) -> ConversationRecord:
    return ConversationRecord(
        id=str(row["id"]),
        title=str(row["title"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_task_id=row["last_task_id"],
        metadata_json=_json_loads(row["metadata_json"]),
    )


def _message_from_row(row: sqlite3.Row) -> MessageRecord:
    return MessageRecord(
        id=str(row["id"]),
        conversation_id=str(row["conversation_id"]),
        role=str(row["role"]),
        content=str(row["content"]),
        task_id=row["task_id"],
        metadata_json=_json_loads(row["metadata_json"]),
        created_at=str(row["created_at"]),
    )


def _task_from_row(row: sqlite3.Row) -> TaskMetadataRecord:
    return TaskMetadataRecord(
        id=str(row["id"]),
        conversation_id=row["conversation_id"],
        status=str(row["status"]),
        task_type=str(row["task_type"]),
        skill_id=row["skill_id"],
        input_json=_json_loads(row["input_json"]),
        run_dir=row["run_dir"],
        error=row["error"],
        error_type=row["error_type"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
