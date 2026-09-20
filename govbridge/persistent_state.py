import json,os,time
try:
 import psycopg
except Exception:
 psycopg=None
DDL="""CREATE SCHEMA IF NOT EXISTS govbridge;
CREATE TABLE IF NOT EXISTS govbridge.spillover_queue(id UUID PRIMARY KEY,segment TEXT NOT NULL,envelope JSONB NOT NULL,state TEXT NOT NULL DEFAULT 'pending',created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.divergence_holds(entity_id TEXT PRIMARY KEY,tier INT NOT NULL,legacy JSONB NOT NULL,modern JSONB NOT NULL,field_name TEXT,state TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.reconciliation_ledger(id BIGSERIAL PRIMARY KEY,entity_id TEXT NOT NULL,event JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.idempotency_keys(message_id TEXT PRIMARY KEY,payload_hash CHAR(64) NOT NULL,result JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT now());\nCREATE TABLE IF NOT EXISTS govbridge.audit_ledger(id BIGSERIAL PRIMARY KEY,event JSONB NOT NULL,previous_hash CHAR(64) NOT NULL,record_hash CHAR(64) UNIQUE NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS spillover_pending_idx ON govbridge.spillover_queue(state,created_at);
CREATE INDEX IF NOT EXISTS reconciliation_entity_idx ON govbridge.reconciliation_ledger(entity_id,created_at DESC);
CREATE TABLE IF NOT EXISTS govbridge.failsafe_dlq(id BIGSERIAL PRIMARY KEY,message_id TEXT,envelope JSONB NOT NULL,error TEXT,state TEXT NOT NULL DEFAULT 'pending',attempt_count INT NOT NULL DEFAULT 0,next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),last_attempt_at TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.manual_holds(id BIGSERIAL PRIMARY KEY,item JSONB NOT NULL,reason TEXT,state TEXT NOT NULL DEFAULT 'manual-hold',created_at TIMESTAMPTZ NOT NULL DEFAULT now());
ALTER TABLE govbridge.failsafe_dlq ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;\nALTER TABLE govbridge.failsafe_dlq ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();\nALTER TABLE govbridge.failsafe_dlq ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;\nCREATE INDEX IF NOT EXISTS failsafe_dlq_state_idx ON govbridge.failsafe_dlq(state,next_attempt_at,created_at);"""
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
def claim_idempotency(message_id,payload_hash):
 if not configured():return None
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("INSERT INTO govbridge.idempotency_keys(message_id,payload_hash) VALUES(%s,%s) ON CONFLICT(message_id) DO NOTHING RETURNING message_id",(message_id,payload_hash))
   if cur.fetchone() is not None:return True
   cur.execute("SELECT payload_hash FROM govbridge.idempotency_keys WHERE message_id=%s",(message_id,));row=cur.fetchone()
   if row and row[0].strip()!=payload_hash:raise ValueError("idempotency_key_payload_conflict")
   return False
def cleanup_idempotency(ttl_seconds=86400):
 if not configured():return 0
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("DELETE FROM govbridge.idempotency_keys WHERE created_at < now()-(%s*interval '1 second')",(max(3600,int(ttl_seconds)),));return cur.rowcount
def append_audit(event,previous_hash,record_hash):
 if not configured():return False
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("INSERT INTO govbridge.audit_ledger(event,previous_hash,record_hash) VALUES(%s::jsonb,%s,%s) ON CONFLICT(record_hash) DO NOTHING",(json.dumps(event),previous_hash,record_hash))
 return True
def audit_events(limit=100):
 if not configured():return []
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:cur.execute("SELECT event FROM govbridge.audit_ledger ORDER BY id DESC LIMIT %s",(min(max(int(limit),1),1000),));return [r[0] for r in reversed(cur.fetchall())]
def advisory_lock(record_key):
 if not configured():return None
 con=psycopg.connect(os.environ["DATABASE_URL"]);cur=con.cursor();cur.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0))",(str(record_key),))
 if cur.fetchone()[0]:return (con,cur)
 cur.close();con.close();return False
def advisory_unlock(handle,record_key):
 if not handle:return False
 con,cur=handle
 try:cur.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))",(str(record_key),));ok=cur.fetchone()[0];con.commit();return ok
 finally:cur.close();con.close()

def add_failsafe_dlq(envelope,error):
 if not configured():return None
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("INSERT INTO govbridge.failsafe_dlq(message_id,envelope,error) VALUES(%s,%s::jsonb,%s) RETURNING id,created_at",(str(envelope.get("message_id") or ""),json.dumps(envelope),str(error)));r=cur.fetchone()
 return {"sequence":r[0],"message_id":envelope.get("message_id"),"envelope":envelope,"error":str(error),"state":"pending","queued_at":r[1].timestamp()}
def failsafe_dlq_items(limit=100):
 if not configured():return []
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("SELECT id,message_id,envelope,error,state,created_at FROM govbridge.failsafe_dlq ORDER BY id DESC LIMIT %s",(min(max(int(limit),1),1000),));rows=cur.fetchall()
 return [{"sequence":r[0],"message_id":r[1],"envelope":r[2],"error":r[3],"state":r[4],"queued_at":r[5].timestamp()} for r in reversed(rows)]
def failsafe_pending(message_id):
 if not configured():return None
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("SELECT id,message_id,envelope,error,state,created_at FROM govbridge.failsafe_dlq WHERE message_id=%s AND state='pending' ORDER BY id DESC LIMIT 1",(message_id,));r=cur.fetchone()
 return None if not r else {"sequence":r[0],"message_id":r[1],"envelope":r[2],"error":r[3],"state":r[4],"queued_at":r[5].timestamp()}
def add_manual_hold(item,reason):
 if not configured():return None
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("INSERT INTO govbridge.manual_holds(item,reason) VALUES(%s::jsonb,%s) RETURNING id,created_at",(json.dumps(item),str(reason)));r=cur.fetchone()
 return {"id":r[0],"item":item,"reason":str(reason),"held_at":r[1].timestamp(),"state":"manual-hold"}
def manual_hold_items(limit=100):
 if not configured():return []
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("SELECT id,item,reason,state,created_at FROM govbridge.manual_holds ORDER BY id DESC LIMIT %s",(min(max(int(limit),1),1000),));rows=cur.fetchall()
 return [{"id":r[0],"item":r[1],"reason":r[2],"state":r[3],"held_at":r[4].timestamp()} for r in reversed(rows)]

def failsafe_self_test():
 if not configured():return {"ok":False,"reason":"postgres_not_configured"}
 marker="selftest-"+str(__import__("uuid").uuid4())
 env={"message_id":marker,"synthetic":True,"purpose":"failsafe-persistence-verification"}
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("INSERT INTO govbridge.failsafe_dlq(message_id,envelope,error) VALUES(%s,%s::jsonb,'self_test') RETURNING id",(marker,json.dumps(env)));dlq_id=cur.fetchone()[0]
   cur.execute("SELECT message_id,envelope,state FROM govbridge.failsafe_dlq WHERE id=%s",(dlq_id,));dlq=cur.fetchone()
   cur.execute("INSERT INTO govbridge.manual_holds(item,reason) VALUES(%s::jsonb,'self_test') RETURNING id",(json.dumps(env),));hold_id=cur.fetchone()[0]
   cur.execute("SELECT item,state FROM govbridge.manual_holds WHERE id=%s",(hold_id,));hold=cur.fetchone()
   cur.execute("DELETE FROM govbridge.failsafe_dlq WHERE id=%s",(dlq_id,))
   cur.execute("DELETE FROM govbridge.manual_holds WHERE id=%s",(hold_id,))
   cur.execute("SELECT EXISTS(SELECT 1 FROM govbridge.failsafe_dlq WHERE id=%s)",(dlq_id,));dlq_remains=cur.fetchone()[0]
   cur.execute("SELECT EXISTS(SELECT 1 FROM govbridge.manual_holds WHERE id=%s)",(hold_id,));hold_remains=cur.fetchone()[0]
 ok=bool(dlq) and dlq[0]==marker and dlq[1].get("message_id")==marker and dlq[2]=="pending" and bool(hold) and hold[0].get("message_id")==marker and hold[1]=="manual-hold" and not dlq_remains and not hold_remains
 return {"ok":ok,"dlq_write_read":bool(dlq),"manual_hold_write_read":bool(hold),"cleanup":not dlq_remains and not hold_remains}

def claim_failsafe_dlq(limit=25):
 if not configured():return []
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   cur.execute("""WITH picked AS (SELECT id FROM govbridge.failsafe_dlq WHERE state='pending' AND next_attempt_at<=now() ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s) UPDATE govbridge.failsafe_dlq q SET state='processing',attempt_count=q.attempt_count+1,last_attempt_at=now() FROM picked WHERE q.id=picked.id RETURNING q.id,q.message_id,q.envelope,q.error,q.attempt_count""",(min(max(int(limit),1),100),));rows=cur.fetchall()
 return [{"sequence":r[0],"message_id":r[1],"envelope":r[2],"error":r[3],"attempt_count":r[4],"state":"processing"} for r in rows]
def finish_failsafe_dlq(sequence,success,error=None,max_attempts=8):
 if not configured():return False
 with psycopg.connect(os.environ["DATABASE_URL"]) as con:
  with con.cursor() as cur:
   if success:cur.execute("UPDATE govbridge.failsafe_dlq SET state='acked',error=NULL WHERE id=%s AND state='processing'",(sequence,))
   else:cur.execute("""UPDATE govbridge.failsafe_dlq SET state=CASE WHEN attempt_count >= %s THEN 'dead' ELSE 'pending' END,error=%s,next_attempt_at=now()+(LEAST(3600,POWER(2,LEAST(attempt_count,11)))::text||' seconds')::interval WHERE id=%s AND state='processing'""",(max_attempts,str(error or "retry_failed"),sequence))
   return cur.rowcount>0
