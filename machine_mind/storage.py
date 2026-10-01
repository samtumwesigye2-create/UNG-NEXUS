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
    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    forgotten BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE machine_mind_events ADD COLUMN IF NOT EXISTS importance DOUBLE PRECISION NOT NULL DEFAULT 0.5;
ALTER TABLE machine_mind_events ADD COLUMN IF NOT EXISTS forgotten BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS machine_mind_belief_history (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    event_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    source_system TEXT,
    belief_json JSONB NOT NULL,
    superseded BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS machine_mind_semantic_memory (
    concept_key TEXT PRIMARY KEY,
    summary_json JSONB NOT NULL,
    support_count BIGINT NOT NULL DEFAULT 1,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    last_reinforced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS machine_mind_learning_log (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT,
    subject TEXT NOT NULL,
    recalled_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    support_count INTEGER NOT NULL DEFAULT 0,
    raw_confidence DOUBLE PRECISION NOT NULL,
    revised_confidence DOUBLE PRECISION NOT NULL,
    learning_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_machine_mind_events_created
    ON machine_mind_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_events_source_type
    ON machine_mind_events(source_system,event_type,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_events_importance
    ON machine_mind_events(forgotten,importance DESC,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_belief_history_subject
    ON machine_mind_belief_history(subject,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_learning_subject
    ON machine_mind_learning_log(subject,created_at DESC);
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

def save_event(event: dict[str, Any], importance: float) -> None:
    conn = connect()
    if conn is None:
        return
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO machine_mind_events(event_id,source_system,event_type,correlation_id,payload_json,event_json,importance)
            VALUES(%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(event_id) DO UPDATE SET importance=GREATEST(machine_mind_events.importance,EXCLUDED.importance)
            """,
            (
                event_id,
                event.get("source_system"),
                str(event.get("event_type") or "event"),
                event.get("correlation_id"),
                Jsonb(event.get("payload") or {}),
                Jsonb(event),
                float(importance),
            ),
        )

def save_belief_version(subject: str, belief: dict[str, Any]) -> None:
    conn = connect()
    if conn is None:
        return
    with conn:
        conn.execute("UPDATE machine_mind_belief_history SET superseded=true WHERE subject=%s AND superseded=false",(subject,))
        conn.execute(
            """
            INSERT INTO machine_mind_belief_history(subject,event_type,confidence,source_system,belief_json)
            VALUES(%s,%s,%s,%s,%s)
            """,
            (
                subject,
                str(belief.get("event_type") or "event"),
                float(belief.get("confidence") or 0.0),
                belief.get("source_system"),
                Jsonb(belief),
            ),
        )

def reinforce_semantic(concept_key: str, summary: dict[str, Any], confidence: float) -> None:
    conn = connect()
    if conn is None:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO machine_mind_semantic_memory(concept_key,summary_json,support_count,confidence,last_reinforced_at,updated_at)
            VALUES(%s,%s,1,%s,now(),now())
            ON CONFLICT(concept_key) DO UPDATE SET
              summary_json=EXCLUDED.summary_json,
              support_count=machine_mind_semantic_memory.support_count+1,
              confidence=EXCLUDED.confidence,
              last_reinforced_at=now(),
              updated_at=now()
            """,
            (concept_key, Jsonb(summary), float(confidence)),
        )

def recall(subject: str, payload: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    conn=connect()
    if conn is None:
        return []
    lim=max(1,min(int(limit),50))
    terms=[str(subject).strip()]
    for key in ("label","data_type","category","entity_id","object_id"):
        value=payload.get(key)
        if value is not None and str(value).strip():
            terms.append(str(value).strip())
    terms=list(dict.fromkeys(t for t in terms if t))
    with conn:
        exact=conn.execute(
            """
            SELECT 'semantic' AS memory_type, concept_key AS memory_key,
                   summary_json AS memory_json, confidence, support_count,
                   updated_at AS memory_time
            FROM machine_mind_semantic_memory
            WHERE concept_key=%s
            LIMIT 1
            """,(subject,)
        ).fetchall()
        pattern="|" .join(terms)
        related=[]
        if pattern:
            related=conn.execute(
                """
                SELECT 'episodic' AS memory_type, event_id AS memory_key,
                       event_json AS memory_json, importance AS confidence,
                       1::bigint AS support_count, created_at AS memory_time
                FROM machine_mind_events
                WHERE forgotten=false
                  AND (payload_json::text ILIKE ANY(%s))
                ORDER BY importance DESC, created_at DESC
                LIMIT %s
                """,
                ([f"%{t}%" for t in terms],lim),
            ).fetchall()
    seen=set()
    result=[]
    for row in list(exact)+list(related):
        key=(row["memory_type"],row["memory_key"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result)>=lim:
            break
    return result

def save_learning(event_id: str | None, subject: str, raw_confidence: float, revised_confidence: float, learning: dict[str, Any]) -> None:
    conn=connect()
    if conn is None:
        return
    with conn:
        conn.execute(
            """
            INSERT INTO machine_mind_learning_log(
                event_id,subject,recalled_count,contradiction_count,support_count,
                raw_confidence,revised_confidence,learning_json
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                event_id,subject,
                int(learning.get("recalled_count",0)),
                int(learning.get("contradiction_count",0)),
                int(learning.get("support_count",0)),
                float(raw_confidence),float(revised_confidence),
                Jsonb(learning),
            ),
        )

def learning_history(subject: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn=connect()
    if conn is None:
        return []
    lim=max(1,min(int(limit),1000))
    with conn:
        if subject:
            return conn.execute(
                """
                SELECT event_id,subject,recalled_count,contradiction_count,support_count,
                       raw_confidence,revised_confidence,learning_json,created_at
                FROM machine_mind_learning_log
                WHERE subject=%s ORDER BY created_at DESC LIMIT %s
                """,(subject,lim)
            ).fetchall()
        return conn.execute(
            """
            SELECT event_id,subject,recalled_count,contradiction_count,support_count,
                   raw_confidence,revised_confidence,learning_json,created_at
            FROM machine_mind_learning_log
            ORDER BY created_at DESC LIMIT %s
            """,(lim,)
        ).fetchall()

def recent_events(limit: int = 100, include_forgotten: bool = False) -> list[dict[str, Any]]:
    conn = connect()
    if conn is None:
        return []
    limit=max(1,min(int(limit),1000))
    where="" if include_forgotten else "WHERE forgotten=false"
    with conn:
        rows=conn.execute(
            f"SELECT event_json FROM machine_mind_events {where} ORDER BY created_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [r["event_json"] for r in reversed(rows)]

def episodes(limit: int = 100, min_importance: float = 0.0) -> list[dict[str, Any]]:
    conn=connect()
    if conn is None:
        return []
    with conn:
        return conn.execute(
            """
            SELECT event_id,source_system,event_type,correlation_id,payload_json,importance,forgotten,created_at
            FROM machine_mind_events
            WHERE forgotten=false AND importance >= %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (float(min_importance),max(1,min(int(limit),1000))),
        ).fetchall()

def semantic_memories(limit: int = 100) -> list[dict[str, Any]]:
    conn=connect()
    if conn is None:
        return []
    with conn:
        return conn.execute(
            """
            SELECT concept_key,summary_json,support_count,confidence,last_reinforced_at,updated_at
            FROM machine_mind_semantic_memory
            ORDER BY support_count DESC, confidence DESC, updated_at DESC
            LIMIT %s
            """,
            (max(1,min(int(limit),1000)),),
        ).fetchall()

def belief_history(subject: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    conn=connect()
    if conn is None:
        return []
    lim=max(1,min(int(limit),1000))
    with conn:
        if subject:
            return conn.execute(
                """
                SELECT subject,event_type,confidence,source_system,belief_json,superseded,created_at
                FROM machine_mind_belief_history
                WHERE subject=%s ORDER BY created_at DESC LIMIT %s
                """,
                (subject,lim),
            ).fetchall()
        return conn.execute(
            """
            SELECT subject,event_type,confidence,source_system,belief_json,superseded,created_at
            FROM machine_mind_belief_history
            ORDER BY created_at DESC LIMIT %s
            """,
            (lim,),
        ).fetchall()

def apply_forgetting() -> dict[str, int]:
    conn=connect()
    if conn is None:
        return {"forgotten":0}
    with conn:
        row=conn.execute(
            """
            WITH marked AS (
              UPDATE machine_mind_events
              SET forgotten=true
              WHERE forgotten=false
                AND importance < 0.35
                AND created_at < now() - interval '30 days'
              RETURNING 1
            )
            SELECT count(*) AS count FROM marked
            """
        ).fetchone()
    return {"forgotten":int(row["count"])}

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
