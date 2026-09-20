import json,os,time
try:
 import psycopg
except Exception:
 psycopg=None
DDL="""CREATE SCHEMA IF NOT EXISTS govbridge;
CREATE TABLE IF NOT EXISTS govbridge.spillover_queue(id UUID PRIMARY KEY,segment TEXT NOT NULL,envelope JSONB NOT NULL,state TEXT NOT NULL DEFAULT 'pending',created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.divergence_holds(entity_id TEXT PRIMARY KEY,tier INT NOT NULL,legacy JSONB NOT NULL,modern JSONB NOT NULL,field_name TEXT,state TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.reconciliation_ledger(id BIGSERIAL PRIMARY KEY,entity_id TEXT NOT NULL,event JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.idempotency_keys(message_id TEXT PRIMARY KEY,payload_hash CHAR(64) NOT NULL,result JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS spillover_pending_idx ON govbridge.spillover_queue(state,created_at);
CREATE INDEX IF NOT EXISTS reconciliation_entity_idx ON govbridge.reconciliation_ledger(entity_id,created_at DESC);"""
def configured():return bool(os.getenv("DATABASE_URL")) and psycopg is not None
def init():
 if not configured():return {"configured":False,"initialized":False}
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute(DDL)
 return {"configured":True,"initialized":True}
def enqueue_spillover(item):
 if not configured():return False
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("INSERT INTO govbridge.spillover_queue(id,segment,envelope,state) VALUES (%s,%s,%s::jsonb,%s) ON CONFLICT(id) DO NOTHING",(item["id"],item.get("segment","async"),json.dumps(item["envelope"]),item.get("state","pending")))
 return True
def spillover(limit=100):
 if not configured():return []
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("SELECT id::text,segment,envelope,state,created_at FROM govbridge.spillover_queue ORDER BY created_at LIMIT %s",(min(int(limit),1000),));return [{"id":r[0],"segment":r[1],"envelope":r[2],"state":r[3],"created_at":r[4].isoformat()} for r in cur.fetchall()]
