CREATE SCHEMA IF NOT EXISTS govbridge;
CREATE TABLE IF NOT EXISTS govbridge.spillover_queue(id UUID PRIMARY KEY,segment TEXT NOT NULL,envelope JSONB NOT NULL,state TEXT NOT NULL DEFAULT 'pending',created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.divergence_holds(entity_id TEXT PRIMARY KEY,tier INT NOT NULL,legacy JSONB NOT NULL,modern JSONB NOT NULL,field_name TEXT,state TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.reconciliation_ledger(id BIGSERIAL PRIMARY KEY,entity_id TEXT NOT NULL,event JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS govbridge.idempotency_keys(message_id TEXT PRIMARY KEY,payload_hash CHAR(64) NOT NULL,result JSONB,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS spillover_pending_idx ON govbridge.spillover_queue(state,created_at);
CREATE INDEX IF NOT EXISTS reconciliation_entity_idx ON govbridge.reconciliation_ledger(entity_id,created_at DESC);
