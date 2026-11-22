-- Migration: Create crop suitability tables
-- MySQL 8.0 compatible. Idempotent: safe to re-run.
-- Run: mysql -u kisaan_user -pshubh1244 kisaan_suvidha < migrations/003_create_crop_suitability_tables.sql

-- 1. Crop categories table
CREATE TABLE IF NOT EXISTS crop_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_crop_categories_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Crops master table with full agronomic parameters
CREATE TABLE IF NOT EXISTS crops (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    scientific_name VARCHAR(100),
    hindi_name VARCHAR(100),
    season ENUM('Kharif', 'Rabi', 'Zaid', 'Perennial') NOT NULL,
    soils JSON,
    n_range_min DECIMAL(5,1),
    n_range_max DECIMAL(5,1),
    p_range_min DECIMAL(5,1),
    p_range_max DECIMAL(5,1),
    k_range_min DECIMAL(5,1),
    k_range_max DECIMAL(5,1),
    ph_range_min DECIMAL(3,1),
    ph_range_max DECIMAL(3,1),
    water_req ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    water_requirement_mm DECIMAL(10,2),
    waterlog_tolerance ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    drought_tolerance ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    temp_min DECIMAL(5,1),
    temp_max DECIMAL(5,1),
    temp_optimal_min DECIMAL(5,1),
    temp_optimal_max DECIMAL(5,1),
    frost_tolerance ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    heat_tolerance ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    wind_tolerance ENUM('Low', 'Medium', 'High') NOT NULL DEFAULT 'Medium',
    crop_duration_days INT,
    sowing_start_month INT,
    sowing_end_month INT,
    harvesting_start_month INT,
    harvesting_end_month INT,
    description TEXT,
    region_desc TEXT,
    source_url TEXT,
    source_name VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES crop_categories(id) ON DELETE CASCADE,
    INDEX idx_crops_name (name),
    INDEX idx_crops_category (category_id),
    INDEX idx_crops_season (season)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Crop regional suitability (state/district level)
CREATE TABLE IF NOT EXISTS crop_regional_suitability (
    id INT AUTO_INCREMENT PRIMARY KEY,
    crop_id INT NOT NULL,
    state_id INT NOT NULL,
    district_id INT NULL,
    suitability_score INT NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (crop_id) REFERENCES crops(id) ON DELETE CASCADE,
    FOREIGN KEY (state_id) REFERENCES states(id) ON DELETE CASCADE,
    FOREIGN KEY (district_id) REFERENCES districts(id) ON DELETE CASCADE,
    UNIQUE KEY unique_crop_location (crop_id, state_id, district_id),
    INDEX idx_crop_regional_crop (crop_id),
    INDEX idx_crop_regional_state (state_id),
    INDEX idx_crop_regional_district (district_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Weather forecasts cache
CREATE TABLE IF NOT EXISTS weather_forecasts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    lat DECIMAL(9,6),
    lon DECIMAL(9,6),
    forecast_date DATE NOT NULL,
    forecast_timestamp BIGINT NOT NULL,
    temp_min DECIMAL(5,1),
    temp_max DECIMAL(5,1),
    temp_avg DECIMAL(5,1),
    humidity_avg DECIMAL(5,1),
    rainfall_mm DECIMAL(10,2),
    wind_speed_max DECIMAL(5,1),
    wind_direction VARCHAR(10),
    weather_condition VARCHAR(100),
    cloud_coverage INT,
    source VARCHAR(50) DEFAULT 'openweathermap',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_weather_location (state, district),
    INDEX idx_weather_date (forecast_date),
    INDEX idx_weather_timestamp (forecast_timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Crop suitability history
CREATE TABLE IF NOT EXISTS crop_suitability_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    crop_id INT NOT NULL,
    state VARCHAR(100) NOT NULL,
    district VARCHAR(100) NOT NULL,
    season ENUM('Kharif', 'Rabi', 'Zaid', 'Perennial') NOT NULL,
    soil_type VARCHAR(50),
    soil_ph DECIMAL(3,1),
    n_value INT,
    p_value INT,
    k_value INT,
    irrigation VARCHAR(50),
    overall_score INT,
    soil_score INT,
    season_score INT,
    region_score INT,
    irrigation_score INT,
    humidity_score INT,
    wind_score INT,
    temperature_score INT,
    rainfall_score INT,
    weather_data JSON,
    analysis_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (crop_id) REFERENCES crops(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_crop_suitability_user (user_id),
    INDEX idx_crop_suitability_crop (crop_id),
    INDEX idx_crop_suitability_date (analysis_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SELECT 'Crop suitability tables migration applied.' AS message;