-- Migration: create Indian LGD location hierarchy tables (State -> District -> Tehsil -> Village)
-- MySQL 8.0 compatible. Idempotent: safe to re-run.
-- Run:  mysql -u kisaan_user -pshubh1244 kisaan_suvidha < migrations/001_create_location_tables.sql

-- 1. States
CREATE TABLE IF NOT EXISTS states (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lgd_code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_states_name (name),
    INDEX idx_states_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Districts
CREATE TABLE IF NOT EXISTS districts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lgd_code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    state_id INT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (state_id) REFERENCES states(id) ON DELETE CASCADE,
    INDEX idx_districts_state (state_id),
    INDEX idx_districts_name (name),
    INDEX idx_districts_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Tehsils / Sub-Districts
CREATE TABLE IF NOT EXISTS tehsils (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lgd_code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    district_id INT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE CASCADE,
    INDEX idx_tehsils_district (district_id),
    INDEX idx_tehsils_name (name),
    INDEX idx_tehsils_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Villages
CREATE TABLE IF NOT EXISTS villages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    lgd_code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    tehsil_id INT NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tehsil_id) REFERENCES tehsils(id) ON DELETE CASCADE,
    INDEX idx_villages_tehsil (tehsil_id),
    INDEX idx_villages_name (name),
    INDEX idx_villages_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. User profiles (persisted location preferences)
-- The application primarily keeps the profile in the session; this table stores
-- the same location IDs/names so data survives across deployments and can be
-- queried directly. Safe to re-run.
CREATE TABLE IF NOT EXISTS user_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mobile VARCHAR(25) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    farm_size VARCHAR(20),
    soil_type VARCHAR(50),
    irrigation VARCHAR(50),
    preferred_language VARCHAR(20) DEFAULT 'English',
    state_id INT NULL,
    district_id INT NULL,
    tehsil_id INT NULL,
    village_id INT NULL,
    state_name VARCHAR(100) NULL,
    district_name VARCHAR(100) NULL,
    tehsil_name VARCHAR(100) NULL,
    village_name VARCHAR(100) NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (state_id) REFERENCES states(id) ON DELETE SET NULL,
    FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE SET NULL,
    FOREIGN KEY (tehsil_id) REFERENCES tehsils(id) ON DELETE SET NULL,
    FOREIGN KEY (village_id) REFERENCES villages(id) ON DELETE SET NULL,
    INDEX idx_user_profiles_mobile (mobile)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT 'Location hierarchy migration applied.' AS message;
