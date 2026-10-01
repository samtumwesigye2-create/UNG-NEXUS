from __future__ import annotations

import json
import os
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except Exception:
    psycopg = None
    dict_row = None
    Jsonb = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

SCHEMA = """
CREATE TABLE IF NOT EXISTS machine_mind_snapshot (
    identity TEXT PRIMARY KEY,
    cycle BIGINT NOT NULL,
    state_json JSONB NOT NULL,
    beliefs_json JSONB NOT NULL,
    goals_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS machine_mind_events (
    event_id TEXT PRIMARY KEY,
    source_system TEXT,
    event_type TEXT NOT NULL,
    correlation_id TEXT,
    payload_json JSONB NOT NULL,
    event_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_machine_mind_events_created
    ON machine_mind_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_events_source_type
    ON machine_mind_events(source_system,event_type,created_at DESC);
"""

def configured() -> bool:
    return bool(DATABASE_URL and psycopg is not None)

def connect():
    if not configured():
        return None
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_schema() -> bool:
    conn = connect()
    if conn is None:
        return False
    with conn:
        conn.execute(SCHEMA)
    return True

def load_snapshot(identity: str) -> dict[str, Any] | None:
    conn = connect()
    if conn is None:
        return None
    with conn:
        return conn.execute(
            "SELECT cycle,state_json,beliefs_json,goals_json,updated_at FROM machine_mind_snapshot WHERE identity=%s",
            (identity,),
        ).fetchone()

def save_snapshot(identity: str, cycle: int, state: dict[str, Any], beliefs: list[dict[str, Any]], goals: list[dict[str, Any]]) -> None:
    conn = connect()
    if conn is None:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO machine_mind_snapshot(identity,cycle,state_json,beliefs_json,goals_json,updated_at)
            VALUES(%s,%s,%s,%s,%s,now())
            ON CONFLICT(identity) DO UPDATE SET
              cycle=EXCLUDED.cycle,
              state_json=EXCLUDED.state_json,
              beliefs_json=EXCLUDED.beliefs_json,
              goals_json=EXCLUDED.goals_json,
              updated_at=now()
            """,
            (identity, cycle, Jsonb(state), Jsonb(beliefs), Jsonb(goals)),
        )

def save_event(event: dict[str, Any]) -> None:
    conn = connect()
    if conn is None:
        return
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO machine_mind_events(event_id,source_system,event_type,correlation_id,payload_json,event_json)
            VALUES(%s,%s,%s,%s,%s,%s)
            ON CONFLICT(event_id) DO NOTHING
            """,
            (
                event_id,
                event.get("source_system"),
                str(event.get("event_type") or "event"),
                event.get("correlation_id"),
                Jsonb(event.get("payload") or {}),
                Jsonb(event),
            ),
        )

def recent_events(limit: int = 100) -> list[dict[str, Any]]:
    conn = connect()
    if conn is None:
        return []
    limit=max(1,min(int(limit),1000))
    with conn:
        rows=conn.execute(
            "SELECT event_json FROM machine_mind_events ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [r["event_json"] for r in reversed(rows)]

def health() -> dict[str, Any]:
    if not configured():
        return {"configured": False, "ready": False}
    try:
        conn=connect()
        with conn:
            row=conn.execute("SELECT now() AS now").fetchone()
        return {"configured": True, "ready": True, "database_time": str(row["now"])}
    except Exception as exc:
        return {"configured": True, "ready": False, "error": type(exc).__name__}
