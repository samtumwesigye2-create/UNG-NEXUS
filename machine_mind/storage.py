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

CREATE TABLE IF NOT EXISTS machine_mind_hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    probability DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    prediction_json JSONB NOT NULL,
    discriminating_observation_json JSONB NOT NULL,
    evidence_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_machine_mind_events_created ON machine_mind_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_events_source_type ON machine_mind_events(source_system,event_type,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_events_importance ON machine_mind_events(forgotten,importance DESC,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_belief_history_subject ON machine_mind_belief_history(subject,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_learning_subject ON machine_mind_learning_log(subject,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_machine_mind_hypotheses_subject ON machine_mind_hypotheses(subject,status,probability DESC);

CREATE TABLE IF NOT EXISTS machine_mind_inquiries (
    inquiry_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    target_system TEXT NOT NULL,
    request_json JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'planned',
    response_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS machine_mind_actions (
    action_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    intended_json JSONB NOT NULL,
    observed_json JSONB,
    prediction_error DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'intended',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS machine_mind_affect (
    cycle BIGINT PRIMARY KEY,
    affect_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS machine_mind_processed_messages (
    message_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    result_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS machine_mind_outbox (
    outbox_id TEXT PRIMARY KEY,
    target_system TEXT NOT NULL,
    message_type TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    correlation_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_machine_mind_outbox_pending ON machine_mind_outbox(status,next_attempt_at,created_at);
"""

def configured() -> bool:
    return bool(DATABASE_URL and psycopg is not None)

def connect():
    if not configured(): return None
    return psycopg.connect(DATABASE_URL,row_factory=dict_row)

def init_schema() -> bool:
    conn=connect()
    if conn is None: return False
    with conn: conn.execute(SCHEMA)
    return True

def load_snapshot(identity):
    conn=connect()
    if conn is None: return None
    with conn:
        return conn.execute("SELECT cycle,state_json,beliefs_json,goals_json,updated_at FROM machine_mind_snapshot WHERE identity=%s",(identity,)).fetchone()

def save_snapshot(identity,cycle,state,beliefs,goals):
    conn=connect()
    if conn is None: return
    with conn:
        conn.execute("""
        INSERT INTO machine_mind_snapshot(identity,cycle,state_json,beliefs_json,goals_json,updated_at)
        VALUES(%s,%s,%s,%s,%s,now())
        ON CONFLICT(identity) DO UPDATE SET cycle=EXCLUDED.cycle,state_json=EXCLUDED.state_json,
        beliefs_json=EXCLUDED.beliefs_json,goals_json=EXCLUDED.goals_json,updated_at=now()
        """,(identity,cycle,Jsonb(state),Jsonb(beliefs),Jsonb(goals)))

def save_event(event,importance):
    conn=connect()
    if conn is None:return
    event_id=str(event.get("event_id") or "")
    if not event_id:return
    with conn:
        conn.execute("""
        INSERT INTO machine_mind_events(event_id,source_system,event_type,correlation_id,payload_json,event_json,importance)
        VALUES(%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(event_id) DO UPDATE SET importance=GREATEST(machine_mind_events.importance,EXCLUDED.importance)
        """,(event_id,event.get("source_system"),str(event.get("event_type") or "event"),event.get("correlation_id"),Jsonb(event.get("payload") or {}),Jsonb(event),float(importance)))

def save_belief_version(subject,belief):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("UPDATE machine_mind_belief_history SET superseded=true WHERE subject=%s AND superseded=false",(subject,))
        conn.execute("INSERT INTO machine_mind_belief_history(subject,event_type,confidence,source_system,belief_json) VALUES(%s,%s,%s,%s,%s)",
                     (subject,str(belief.get("event_type") or "event"),float(belief.get("confidence") or 0.0),belief.get("source_system"),Jsonb(belief)))

def reinforce_semantic(concept_key,summary,confidence):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""
        INSERT INTO machine_mind_semantic_memory(concept_key,summary_json,support_count,confidence,last_reinforced_at,updated_at)
        VALUES(%s,%s,1,%s,now(),now())
        ON CONFLICT(concept_key) DO UPDATE SET summary_json=EXCLUDED.summary_json,
        support_count=machine_mind_semantic_memory.support_count+1,confidence=EXCLUDED.confidence,last_reinforced_at=now(),updated_at=now()
        """,(concept_key,Jsonb(summary),float(confidence)))

def recall(subject,payload,limit=12):
    conn=connect()
    if conn is None:return []
    lim=max(1,min(int(limit),50))
    terms=[str(subject).strip()]
    for key in ("label","data_type","category","entity_id","object_id"):
        v=payload.get(key)
        if v is not None and str(v).strip():terms.append(str(v).strip())
    terms=list(dict.fromkeys(t for t in terms if t))
    with conn:
        exact=conn.execute("""
        SELECT 'semantic' AS memory_type,concept_key AS memory_key,summary_json AS memory_json,
        confidence,support_count,updated_at AS memory_time FROM machine_mind_semantic_memory
        WHERE concept_key=%s LIMIT 1
        """,(subject,)).fetchall()
        related=[]
        if terms:
            related=conn.execute("""
            SELECT 'episodic' AS memory_type,event_id AS memory_key,event_json AS memory_json,
            importance AS confidence,1::bigint AS support_count,created_at AS memory_time
            FROM machine_mind_events WHERE forgotten=false AND (payload_json::text ILIKE ANY(%s))
            ORDER BY importance DESC,created_at DESC LIMIT %s
            """,([f"%{t}%" for t in terms],lim)).fetchall()
    seen=set();result=[]
    for row in list(exact)+list(related):
        key=(row["memory_type"],row["memory_key"])
        if key in seen:continue
        seen.add(key);result.append(row)
        if len(result)>=lim:break
    return result

def save_learning(event_id,subject,raw_confidence,revised_confidence,learning):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""
        INSERT INTO machine_mind_learning_log(event_id,subject,recalled_count,contradiction_count,support_count,raw_confidence,revised_confidence,learning_json)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
        """,(event_id,subject,int(learning.get("recalled_count",0)),int(learning.get("contradiction_count",0)),int(learning.get("support_count",0)),float(raw_confidence),float(revised_confidence),Jsonb(learning)))

def learning_history(subject=None,limit=100):
    conn=connect()
    if conn is None:return []
    lim=max(1,min(int(limit),1000))
    with conn:
        if subject:
            return conn.execute("""
            SELECT event_id,subject,recalled_count,contradiction_count,support_count,raw_confidence,revised_confidence,learning_json,created_at
            FROM machine_mind_learning_log WHERE subject=%s ORDER BY created_at DESC LIMIT %s
            """,(subject,lim)).fetchall()
        return conn.execute("""
        SELECT event_id,subject,recalled_count,contradiction_count,support_count,raw_confidence,revised_confidence,learning_json,created_at
        FROM machine_mind_learning_log ORDER BY created_at DESC LIMIT %s
        """,(lim,)).fetchall()

def replace_hypotheses(subject,hypotheses):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("UPDATE machine_mind_hypotheses SET status='superseded',updated_at=now() WHERE subject=%s AND status='active'",(subject,))
        for h in hypotheses:
            conn.execute("""
            INSERT INTO machine_mind_hypotheses(hypothesis_id,subject,description,probability,status,prediction_json,discriminating_observation_json,evidence_json)
            VALUES(%s,%s,%s,%s,'active',%s,%s,%s)
            ON CONFLICT(hypothesis_id) DO UPDATE SET probability=EXCLUDED.probability,status='active',
            prediction_json=EXCLUDED.prediction_json,discriminating_observation_json=EXCLUDED.discriminating_observation_json,
            evidence_json=EXCLUDED.evidence_json,updated_at=now()
            """,(h["hypothesis_id"],subject,h["description"],float(h["probability"]),Jsonb(h["prediction"]),Jsonb(h["next_observation"]),Jsonb(h["evidence"])))

def hypotheses(subject=None,limit=100):
    conn=connect()
    if conn is None:return []
    lim=max(1,min(int(limit),1000))
    with conn:
        if subject:
            return conn.execute("""
            SELECT hypothesis_id,subject,description,probability,status,prediction_json,discriminating_observation_json,evidence_json,created_at,updated_at
            FROM machine_mind_hypotheses WHERE subject=%s AND status='active' ORDER BY probability DESC LIMIT %s
            """,(subject,lim)).fetchall()
        return conn.execute("""
        SELECT hypothesis_id,subject,description,probability,status,prediction_json,discriminating_observation_json,evidence_json,created_at,updated_at
        FROM machine_mind_hypotheses WHERE status='active' ORDER BY updated_at DESC,probability DESC LIMIT %s
        """,(lim,)).fetchall()

def recent_events(limit=100,include_forgotten=False):
    conn=connect()
    if conn is None:return []
    limit=max(1,min(int(limit),1000));where="" if include_forgotten else "WHERE forgotten=false"
    with conn:
        rows=conn.execute(f"SELECT event_json FROM machine_mind_events {where} ORDER BY created_at DESC LIMIT %s",(limit,)).fetchall()
    return [r["event_json"] for r in reversed(rows)]

def episodes(limit=100,min_importance=0.0):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""
        SELECT event_id,source_system,event_type,correlation_id,payload_json,importance,forgotten,created_at
        FROM machine_mind_events WHERE forgotten=false AND importance >= %s ORDER BY created_at DESC LIMIT %s
        """,(float(min_importance),max(1,min(int(limit),1000)))).fetchall()

def semantic_memories(limit=100):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""
        SELECT concept_key,summary_json,support_count,confidence,last_reinforced_at,updated_at
        FROM machine_mind_semantic_memory ORDER BY support_count DESC,confidence DESC,updated_at DESC LIMIT %s
        """,(max(1,min(int(limit),1000)),)).fetchall()

def belief_history(subject=None,limit=100):
    conn=connect()
    if conn is None:return []
    lim=max(1,min(int(limit),1000))
    with conn:
        if subject:
            return conn.execute("""
            SELECT subject,event_type,confidence,source_system,belief_json,superseded,created_at
            FROM machine_mind_belief_history WHERE subject=%s ORDER BY created_at DESC LIMIT %s
            """,(subject,lim)).fetchall()
        return conn.execute("""
        SELECT subject,event_type,confidence,source_system,belief_json,superseded,created_at
        FROM machine_mind_belief_history ORDER BY created_at DESC LIMIT %s
        """,(lim,)).fetchall()

def apply_forgetting():
    conn=connect()
    if conn is None:return {"forgotten":0}
    with conn:
        row=conn.execute("""
        WITH marked AS (
          UPDATE machine_mind_events SET forgotten=true
          WHERE forgotten=false AND importance < 0.35 AND created_at < now() - interval '30 days'
          RETURNING 1
        ) SELECT count(*) AS count FROM marked
        """).fetchone()
    return {"forgotten":int(row["count"])}

def health():
    if not configured():return {"configured":False,"ready":False}
    try:
        conn=connect()
        with conn:row=conn.execute("SELECT now() AS now").fetchone()
        return {"configured":True,"ready":True,"database_time":str(row["now"])}
    except Exception as exc:
        return {"configured":True,"ready":False,"error":type(exc).__name__}


def save_inquiry(inquiry):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""INSERT INTO machine_mind_inquiries(inquiry_id,subject,target_system,request_json,status)
        VALUES(%s,%s,%s,%s,%s)
        ON CONFLICT(inquiry_id) DO UPDATE SET request_json=EXCLUDED.request_json,status=EXCLUDED.status,updated_at=now()""",
        (inquiry["inquiry_id"],inquiry["subject"],inquiry["target_system"],Jsonb(inquiry),inquiry.get("status","planned")))

def inquiries(limit=100):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""SELECT inquiry_id,subject,target_system,request_json,status,response_json,created_at,updated_at
        FROM machine_mind_inquiries ORDER BY created_at DESC LIMIT %s""",(max(1,min(int(limit),1000)),)).fetchall()

def save_action(action):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""INSERT INTO machine_mind_actions(action_id,subject,intended_json,observed_json,prediction_error,status)
        VALUES(%s,%s,%s,%s,%s,%s)
        ON CONFLICT(action_id) DO UPDATE SET observed_json=EXCLUDED.observed_json,prediction_error=EXCLUDED.prediction_error,status=EXCLUDED.status,updated_at=now()""",
        (action["action_id"],action["subject"],Jsonb(action.get("intended") or {}),Jsonb(action.get("observed")) if action.get("observed") is not None else None,action.get("prediction_error"),action.get("status","intended")))

def actions(limit=100):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""SELECT action_id,subject,intended_json,observed_json,prediction_error,status,created_at,updated_at
        FROM machine_mind_actions ORDER BY created_at DESC LIMIT %s""",(max(1,min(int(limit),1000)),)).fetchall()

def save_affect(cycle,affect):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""INSERT INTO machine_mind_affect(cycle,affect_json) VALUES(%s,%s)
        ON CONFLICT(cycle) DO UPDATE SET affect_json=EXCLUDED.affect_json""",(int(cycle),Jsonb(affect)))

def recent_affect(limit=100):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""SELECT cycle,affect_json,created_at FROM machine_mind_affect ORDER BY cycle DESC LIMIT %s""",(max(1,min(int(limit),1000)),)).fetchall()


def begin_message(message_id):
    conn=connect()
    if conn is None:return True,None
    with conn:
        row=conn.execute("""INSERT INTO machine_mind_processed_messages(message_id,status)
        VALUES(%s,'processing') ON CONFLICT(message_id) DO NOTHING RETURNING message_id""",(message_id,)).fetchone()
        if row:return True,None
        existing=conn.execute("SELECT status,result_json FROM machine_mind_processed_messages WHERE message_id=%s",(message_id,)).fetchone()
        return False,existing

def finish_message(message_id,result):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""UPDATE machine_mind_processed_messages SET status='done',result_json=%s,updated_at=now()
        WHERE message_id=%s""",(Jsonb(result),message_id))

def enqueue_outbox(outbox_id,target_system,message_type,payload,correlation_id=None):
    conn=connect()
    if conn is None:return
    with conn:
        conn.execute("""INSERT INTO machine_mind_outbox(outbox_id,target_system,message_type,payload_json,correlation_id)
        VALUES(%s,%s,%s,%s,%s) ON CONFLICT(outbox_id) DO NOTHING""",
        (outbox_id,target_system,message_type,Jsonb(payload),correlation_id))

def pending_outbox(limit=20):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""SELECT outbox_id,target_system,message_type,payload_json,correlation_id,attempts
        FROM machine_mind_outbox WHERE status='pending' AND next_attempt_at<=now()
        ORDER BY created_at ASC LIMIT %s""",(max(1,min(int(limit),100)),)).fetchall()

def mark_outbox(outbox_id,sent,error=None):
    conn=connect()
    if conn is None:return
    with conn:
        if sent:
            conn.execute("""UPDATE machine_mind_outbox SET status='sent',attempts=attempts+1,last_error=NULL,updated_at=now()
            WHERE outbox_id=%s""",(outbox_id,))
        else:
            conn.execute("""UPDATE machine_mind_outbox SET attempts=attempts+1,last_error=%s,
            status=CASE WHEN attempts+1>=8 THEN 'dead' ELSE 'pending' END,
            next_attempt_at=now() + (LEAST(300, power(2, LEAST(attempts+1,8))::int) * interval '1 second'),
            updated_at=now() WHERE outbox_id=%s""",(error,outbox_id))

def outbox_status(limit=100):
    conn=connect()
    if conn is None:return []
    with conn:
        return conn.execute("""SELECT outbox_id,target_system,message_type,correlation_id,status,attempts,last_error,next_attempt_at,created_at,updated_at
        FROM machine_mind_outbox ORDER BY created_at DESC LIMIT %s""",(max(1,min(int(limit),1000)),)).fetchall()
