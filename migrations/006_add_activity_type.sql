-- Migration: Add activity_type column to crop_suitability_history
-- MySQL 8.0 compatible. Idempotent: safe to re-run.
-- Run: mysql -u kisaan_user -pshubh1244 kisaan_suvidha < migrations/006_add_activity_type.sql

ALTER TABLE crop_suitability_history
ADD COLUMN activity_type VARCHAR(50) NULL AFTER overall_score;

SELECT 'activity_type column added to crop_suitability_history.' AS message;
