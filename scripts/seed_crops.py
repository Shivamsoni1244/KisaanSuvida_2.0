#!/usr/bin/env python3
"""
Seed script to populate crop database with common Indian crops.
Run: python scripts/seed_crops.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.db import get_db

# Common Indian crops with agronomic data
CROPS = [
    {
        "name": "Rice (Paddy)",
        "hindi_name": "धान (चावल)",
        "scientific_name": "Oryza sativa",
        "season": "Kharif",
        "soils": ["Alluvial", "Clayey", "Black"],
        "n_range_min": 70, "n_range_max": 115,
        "p_range_min": 30, "p_range_max": 60,
        "k_range_min": 30, "k_range_max": 60,
        "ph_range_min": 5.5, "ph_range_max": 7.5,
        "water_req": "High",
        "water_requirement_mm": 1200,
        "soil_compatibility": 96,
        "season_compatibility": 98,
        "regional_compatibility": 89,
        "irrigation_compatibility": 95,
        "base_ml_prob": 92,
        "base_hybrid": 94,
    },
    {
        "name": "Wheat",
        "hindi_name": "गेहूं",
        "scientific_name": "Triticum aestivum",
        "season": "Rabi",
        "soils": ["Alluvial", "Clayey", "Black"],
        "n_range_min": 80, "n_range_max": 120,
        "p_range_min": 40, "p_range_max": 60,
        "k_range_min": 30, "k_range_max": 50,
        "ph_range_min": 6.0, "ph_range_max": 7.5,
        "water_req": "Medium",
        "water_requirement_mm": 450,
        "soil_compatibility": 96,
        "season_compatibility": 98,
        "regional_compatibility": 92,
        "irrigation_compatibility": 90,
        "base_ml_prob": 95,
        "base_hybrid": 96,
    },
    {
        "name": "Maize",
        "hindi_name": "मक्का",
        "scientific_name": "Zea mays",
        "season": "Kharif",
        "soils": ["Alluvial", "Red", "Sandy loam", "Black"],
        "n_range_min": 60, "n_range_max": 100,
        "p_range_min": 35, "p_range_max": 65,
        "k_range_min": 30, "k_range_max": 50,
        "ph_range_min": 5.8, "ph_range_max": 7.5,
        "water_req": "Medium",
        "water_requirement_mm": 550,
        "soil_compatibility": 92,
        "season_compatibility": 90,
        "regional_compatibility": 85,
        "irrigation_compatibility": 90,
        "base_ml_prob": 84,
        "base_hybrid": 87,
    },
    {
        "name": "Pearl millet",
        "hindi_name": "बाजरा",
        "scientific_name": "Pennisetum glaucum",
        "season": "Kharif",
        "soils": ["Sandy loam", "Red", "Alluvial"],
        "n_range_min": 40, "n_range_max": 80,
        "p_range_min": 20, "p_range_max": 45,
        "k_range_min": 20, "k_range_max": 45,
        "ph_range_min": 6.0, "ph_range_max": 8.0,
        "water_req": "Low",
        "water_requirement_mm": 350,
        "soil_compatibility": 85,
        "season_compatibility": 90,
        "regional_compatibility": 80,
        "irrigation_compatibility": 95,
        "base_ml_prob": 79,
        "base_hybrid": 81,
    },
    {
        "name": "Wheat",
        "hindi_name": "गेहूं",
        "scientific_name": "Triticum aestivum",
        "season": "Rabi",
        "soils": ["Alluvial", "Clayey", "Black"],
        "n_range_min": 80, "n_range_max": 120,
        "p_range_min": 40, "p_range_max": 60,
        "k_range_min": 30, "k_range_max": 50,
        "ph_range_min": 6.0, "ph_range_max": 7.5,
        "water_req": "Medium",
        "water_requirement_mm": 450,
        "soil_compatibility": 96,
        "season_compatibility": 98,
        "regional_compatibility": 92,
        "irrigation_compatibility": 90,
        "base_ml_prob": 95,
        "base_hybrid": 96,
    },
    {
        "name": "Cotton",
        "hindi_name": "कपास",
        "scientific_name": "Gossypium hirsutum",
        "season": "Kharif",
        "soils": ["Black", "Alluvial", "Clayey"],
        "n_range_min": 70, "n_range_max": 110,
        "p_range_min": 30, "p_range_max": 55,
        "k_range_min": 35, "k_range_max": 60,
        "ph_range_min": 6.5, "ph_range_max": 8.2,
        "water_req": "Medium",
        "water_requirement_mm": 700,
        "soil_compatibility": 90,
        "season_compatibility": 92,
        "regional_compatibility": 85,
        "irrigation_compatibility": 90,
        "base_ml_prob": 82,
        "base_hybrid": 85,
    },
    {
        "name": "Sugarcane",
        "hindi_name": "गन्ना",
        "scientific_name": "Saccharum officinarum",
        "season": "Kharif",
        "soils": ["Alluvial", "Clayey", "Black"],
        "n_range_min": 100, "n_range_max": 150,
        "p_range_min": 50, "p_range_max": 75,
        "k_range_min": 50, "k_range_max": 80,
        "ph_range_min": 6.5, "ph_range_max": 7.8,
        "water_req": "High",
        "water_requirement_mm": 1500,
        "soil_compatibility": 90,
        "season_compatibility": 88,
        "regional_compatibility": 85,
        "irrigation_compatibility": 90,
        "base_ml_prob": 76,
        "base_hybrid": 78,
    },
    {
        "name": "Gram (Chickpea)",
        "hindi_name": "चना",
        "scientific_name": "Cicer arietinum",
        "season": "Rabi",
        "soils": ["Sandy loam", "Alluvial", "Red"],
        "n_range_min": 20, "n_range_max": 45,
        "p_range_min": 40, "p_range_max": 60,
        "k_range_min": 20, "k_range_max": 40,
        "ph_range_min": 6.0, "ph_range_max": 7.5,
        "water_req": "Low",
        "water_requirement_mm": 350,
        "soil_compatibility": 88,
        "season_compatibility": 90,
        "regional_compatibility": 85,
        "irrigation_compatibility": 90,
        "base_ml_prob": 88,
        "base_hybrid": 89,
    },
    {
        "name": "Potato",
        "hindi_name": "आलू",
        "scientific_name": "Solanum tuberosum",
        "season": "Rabi",
        "soils": ["Sandy loam", "Alluvial"],
        "n_range_min": 90, "n_range_max": 130,
        "p_range_min": 50, "p_range_max": 80,
        "k_range_min": 60, "k_range_max": 100,
        "ph_range_min": 5.2, "ph_range_max": 6.8,
        "water_req": "Medium",
        "water_requirement_mm": 500,
        "soil_compatibility": 85,
        "season_compatibility": 90,
        "regional_compatibility": 85,
        "irrigation_compatibility": 90,
        "base_ml_prob": 90,
        "base_hybrid": 91,
    },
    {
        "name": "Sugarcane",
        "hindi_name": "गन्ना",
        "scientific_name": "Saccharum officinarum",
        "season": "Kharif",
        "soils": ["Alluvial", "Clayey", "Black"],
        "n_range_min": 100, "n_range_max": 150,
        "p_range_min": 50, "p_range_max": 75,
        "k_range_min": 50, "k_range_max": 80,
        "ph_range_min": 6.5, "ph_range_max": 7.8,
        "water_req": "High",
        "water_requirement_mm": 1500,
        "soil_compatibility": 90,
        "season_compatibility": 88,
        "regional_compatibility": 85,
        "irrigation_compatibility": 90,
        "base_ml_prob": 76,
        "base_hybrid": 78,
    },
]

INSERT_SQL = """
INSERT INTO crops (
    name, hindi_name, scientific_name, season,
    soils, n_range_min, n_range_max,
    p_range_min, p_range_max,
    k_range_min, k_range_max,
    ph_range_min, ph_range_max,
    water_req, water_requirement_mm,
    soil_compatibility, season_compatibility, regional_compatibility,
    irrigation_compatibility, base_ml_prob, base_hybrid
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

def main():
    conn = get_db()
    cur = conn.cursor()
    
    print("Inserting crops...")
    count = 0
    for crop in CROPS:
        try:
            cur.execute(INSERT_SQL, (
                crop["name"], crop["hindi_name"], crop["scientific_name"],
                crop["season"],
                ",".join(crop["soils"]),
                crop["n_range_min"], crop["n_range_max"],
                crop["p_range_min"], crop["p_range_max"],
                crop["k_range_min"], crop["k_range_max"],
                crop["ph_range_min"], crop["ph_range_max"],
                crop["water_req"], crop["water_requirement_mm"],
                crop["soil_compatibility"], crop["season_compatibility"], crop["regional_compatibility"],
                crop["irrigation_compatibility"], crop["base_ml_prob"], crop["base_hybrid"],
            ))
            count += 1
        except Exception as e:
            print(f"Error inserting {crop['name']}: {e}")
    
    conn.commit()
    print(f"\nSuccessfully inserted {count} crops into database!")

if __name__ == "__main__":
    main()