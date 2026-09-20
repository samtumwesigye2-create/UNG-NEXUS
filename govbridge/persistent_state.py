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

def self_test():
 if not configured():return {"ok":False,"reason":"postgres_not_configured"}
 import uuid
 marker=str(uuid.uuid4())
 envelope={"synthetic":True,"purpose":"persistence-verification","marker":marker}
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("INSERT INTO govbridge.spillover_queue(id,segment,envelope,state) VALUES (%s,'async',%s::jsonb,'pending')",(marker,json.dumps(envelope)))
   cur.execute("SELECT envelope,state FROM govbridge.spillover_queue WHERE id=%s",(marker,))
   row=cur.fetchone()
   cur.execute("DELETE FROM govbridge.spillover_queue WHERE id=%s",(marker,))
   cur.execute("SELECT EXISTS(SELECT 1 FROM govbridge.spillover_queue WHERE id=%s)",(marker,))
   remains=cur.fetchone()[0]
 return {"ok":bool(row) and row[0].get("marker")==marker and row[1]=="pending" and not remains,
         "write":bool(row),"readback":bool(row),"cleanup":not remains}

def put_divergence_hold(entity_id,tier,legacy,modern,field_name,state="manual-review"):
 if not configured():return False
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("""INSERT INTO govbridge.divergence_holds(entity_id,tier,legacy,modern,field_name,state) VALUES(%s,%s,%s::jsonb,%s::jsonb,%s,%s) ON CONFLICT(entity_id) DO UPDATE SET tier=EXCLUDED.tier,legacy=EXCLUDED.legacy,modern=EXCLUDED.modern,field_name=EXCLUDED.field_name,state=EXCLUDED.state,updated_at=now()""",(entity_id,tier,json.dumps(legacy),json.dumps(modern),field_name,state))
 return True
def get_divergence_hold(entity_id):
 if not configured():return None
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("SELECT tier,legacy,modern,field_name,state,created_at,updated_at FROM govbridge.divergence_holds WHERE entity_id=%s",(entity_id,));r=cur.fetchone()
 return None if not r else {"entity_id":entity_id,"tier":r[0],"legacy":r[1],"modern":r[2],"field":r[3],"state":r[4],"created_at":r[5].isoformat(),"updated_at":r[6].isoformat()}
def resolve_divergence_hold(entity_id):
 if not configured():return False
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("UPDATE govbridge.divergence_holds SET state='resolved',updated_at=now() WHERE entity_id=%s",(entity_id,));return cur.rowcount>0
def append_reconciliation_event(entity_id,event):
 if not configured():return False
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("INSERT INTO govbridge.reconciliation_ledger(entity_id,event) VALUES(%s,%s::jsonb)",(entity_id,json.dumps(event)))
 return True
def reconciliation_events(limit=1000):
 if not configured():return []
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("SELECT event FROM govbridge.reconciliation_ledger ORDER BY id DESC LIMIT %s",(min(max(int(limit),1),5000),));return [r[0] for r in reversed(cur.fetchall())]
def claim_idempotency(message_id,payload_hash="0"*64):
 if not configured():return None
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("INSERT INTO govbridge.idempotency_keys(message_id,payload_hash) VALUES(%s,%s) ON CONFLICT(message_id) DO NOTHING RETURNING message_id",(message_id,payload_hash));return cur.fetchone() is not None
