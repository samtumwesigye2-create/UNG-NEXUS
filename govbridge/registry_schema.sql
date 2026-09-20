CREATE SCHEMA IF NOT EXISTS registry;
DO $$ BEGIN CREATE TYPE registry.operational_status AS ENUM ('ACTIVE','DECEASED','UNDER_REVIEW','SUSPENDED'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE TABLE IF NOT EXISTS registry.identity_profiles (
 profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), national_id_hash CHAR(64) NOT NULL UNIQUE,
 encrypted_pii BYTEA NOT NULL, family_name VARCHAR(100) NOT NULL, given_names VARCHAR(100) NOT NULL,
 date_of_birth DATE, status registry.operational_status NOT NULL DEFAULT 'ACTIVE',
 metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS registry.addresses (
 address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), profile_id UUID REFERENCES registry.identity_profiles(profile_id) ON DELETE CASCADE,
 is_primary BOOLEAN DEFAULT true, street_address VARCHAR(255), locality VARCHAR(100), postal_code VARCHAR(20),
 country_code CHAR(2), valid_from TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, valid_to TIMESTAMPTZ);
