-- Migration: Create mandi_sync_status table for tracking mandi price sync jobs
-- MySQL 8.0 compatible. Idempotent: safe to re-run.
-- Run: mysql -u kisaan_user -pshubh1244 kisaan_suvidha < migrations/005_create_mandi_sync_status_table.sql
-- (The service layer also creates this table idempotently on first use.)

CREATE TABLE IF NOT EXISTS mandi_sync_status (
    job_id VARCHAR(64) PRIMARY KEY,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filters TEXT,
    max_records INT DEFAULT 5000,
    fetched INT DEFAULT 0,
    inserted INT DEFAULT 0,
    updated INT DEFAULT 0,
    error TEXT,
    started_at TIMESTAMP NULL DEFAULT NULL,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT 'Mandi sync status table migration applied.' AS message;
