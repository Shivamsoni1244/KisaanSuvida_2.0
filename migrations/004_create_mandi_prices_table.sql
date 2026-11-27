-- Migration: Create mandi_prices table for the Mandi Prices module
-- MySQL 8.0 compatible. Idempotent: safe to re-run.
-- Run: mysql -u kisaan_user -pshubh1244 kisaan_suvidha < migrations/004_create_mandi_prices_table.sql

CREATE TABLE IF NOT EXISTS mandi_prices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    market VARCHAR(150) NOT NULL,
    commodity VARCHAR(150) NOT NULL,
    variety VARCHAR(100),
    grade VARCHAR(100),
    arrival_date DATE NOT NULL,
    min_price DECIMAL(10,2),
    max_price DECIMAL(10,2),
    modal_price DECIMAL(10,2),
    source VARCHAR(100) DEFAULT 'data.gov.in AGMARKNET',
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_mandi_record (market, commodity, variety, grade, arrival_date),
    INDEX idx_mandi_market (market),
    INDEX idx_mandi_commodity (commodity),
    INDEX idx_mandi_location (state, district),
    INDEX idx_mandi_arrival_date (arrival_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT 'Mandi prices table migration applied.' AS message;
