"""
services/crop_service.py - Crop database service for Kisaan Suvidha

Handles all database operations for crops and crop recommendation history:
- Search crops by name
- Get crop details by ID
- Get crops by category
- Get all crops
- Save recommendation history
- Retrieve recommendation history
- Crop regional suitability

Uses MySQL connection pool from data/db.py
"""

import logging
from typing import Any, Dict, List, Optional

from data.db import get_db

logger = logging.getLogger(__name__)


def search_crops(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Search crops by name (fuzzy match).

    Args:
        query: Search string
        limit: Maximum number of results

    Returns:
        List of crop dictionaries
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.id, c.name, c.hindi_name, c.season, c.water_req,
                   c.crop_duration_days, c.description,
                   cc.name as category_name
            FROM crops c
            LEFT JOIN crop_categories cc ON c.category_id = cc.id
            WHERE c.is_active = 1
              AND (c.name LIKE %s OR c.hindi_name LIKE %s OR c.scientific_name LIKE %s)
            ORDER BY c.name
            LIMIT %s
            """,
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        )
        return cur.fetchall() or []
    except Exception as e:
        logger.error(f"Error searching crops: {e}")
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_crop_by_id(crop_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a single crop by its ID.

    Args:
        crop_id: Crop ID

    Returns:
        Crop dictionary or None
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.*, cc.name as category_name
            FROM crops c
            LEFT JOIN crop_categories cc ON c.category_id = cc.id
            WHERE c.id = %s AND c.is_active = 1
            """,
            (crop_id,),
        )
        return cur.fetchone()
    except Exception as e:
        logger.error(f"Error getting crop by id {crop_id}: {e}")
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_all_crops(limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get all active crops.

    Args:
        limit: Maximum number of crops to return

    Returns:
        List of crop dictionaries
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.id, c.name, c.hindi_name, c.season, c.water_req,
                   c.crop_duration_days, c.description,
                   cc.name as category_name
            FROM crops c
            LEFT JOIN crop_categories cc ON c.category_id = cc.id
            WHERE c.is_active = 1
            ORDER BY c.name
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall() or []
    except Exception as e:
        logger.error(f"Error getting all crops: {e}")
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_crops_by_category(category: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get crops filtered by category name.

    Args:
        category: Category name
        limit: Maximum number of crops to return

    Returns:
        List of crop dictionaries
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT c.id, c.name, c.hindi_name, c.season, c.water_req,
                   c.crop_duration_days, c.description,
                   cc.name as category_name
            FROM crops c
            LEFT JOIN crop_categories cc ON c.category_id = cc.id
            WHERE c.is_active = 1 AND cc.name = %s
            ORDER BY c.name
            LIMIT %s
            """,
            (category, limit),
        )
        return cur.fetchall() or []
    except Exception as e:
        logger.error(f"Error getting crops by category {category}: {e}")
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_all_categories() -> List[Dict[str, Any]]:
    """
    Get all active crop categories.

    Returns:
        List of category dictionaries
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, name, description
            FROM crop_categories
            WHERE is_active = 1
            ORDER BY name
            """
        )
        return cur.fetchall() or []
    except Exception as e:
        logger.error(f"Error getting crop categories: {e}")
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def save_recommendation_history(
    user_id: int,
    crop_id: int,
    state: str,
    district: str,
    season: str,
    soil_type: str,
    soil_ph: float,
    n_value: int,
    p_value: int,
    k_value: int,
    irrigation: str,
    overall_score: int,
    soil_score: int,
    season_score: int,
    region_score: int,
    irrigation_score: int,
    humidity_score: int,
    wind_score: int,
    temperature_score: int,
    rainfall_score: int,
    weather_data: dict,
) -> Optional[int]:
    """
    Save a crop suitability recommendation to history.

    Args:
        user_id: User ID
        crop_id: Crop ID
        state: State name
        district: District name
        season: Season
        soil_type: Soil type
        soil_ph: Soil pH
        n_value: Nitrogen value
        p_value: Phosphorus value
        k_value: Potassium value
        irrigation: Irrigation type
        overall_score: Overall suitability score
        soil_score: Soil compatibility score
        season_score: Season compatibility score
        region_score: Regional compatibility score
        irrigation_score: Irrigation compatibility score
        humidity_score: Humidity score
        wind_score: Wind score
        temperature_score: Temperature score
        rainfall_score: Rainfall score
        weather_data: Weather data as dict

    Returns:
        ID of inserted record or None on failure
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        import json as json_module

        cur.execute(
            """
            INSERT INTO crop_suitability_history (
                user_id, crop_id, state, district, season,
                soil_type, soil_ph, n_value, p_value, k_value,
                irrigation, overall_score, soil_score, season_score,
                region_score, irrigation_score, humidity_score,
                wind_score, temperature_score, rainfall_score,
                weather_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id, crop_id, state, district, season,
                soil_type, soil_ph, n_value, p_value, k_value,
                irrigation, overall_score, soil_score, season_score,
                region_score, irrigation_score, humidity_score,
                wind_score, temperature_score, rainfall_score,
                json_module.dumps(weather_data) if weather_data else None,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"Error saving recommendation history: {e}")
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_crop_recommendation_history(
    user_id: int,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Get recommendation history for a user.

    Args:
        user_id: User ID
        limit: Maximum number of records

    Returns:
        List of history dictionaries
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT h.*, c.name as crop_name
            FROM crop_suitability_history h
            LEFT JOIN crops c ON h.crop_id = c.id
            WHERE h.user_id = %s
            ORDER BY h.analysis_date DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return cur.fetchall() or []
    except Exception as e:
        logger.error(f"Error getting recommendation history: {e}")
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_crop_regional_suitability(
    crop_id: int, state: str, district: str = None
) -> Optional[Dict[str, Any]]:
    """
    Get regional compatibility score for a crop in a specific state/district.

    Args:
        crop_id: Crop ID
        state: State name
        district: District name (optional)

    Returns:
        Dict with compatibility score or None
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        if district:
            cur.execute(
                """
                SELECT crs.*, c.name as crop_name
                FROM crop_regional_suitability crs
                JOIN crops c ON crs.crop_id = c.id
                JOIN states s ON crs.state_id = s.id
                LEFT JOIN districts d ON crs.district_id = d.id
                WHERE crs.crop_id = %s AND s.name = %s AND d.name = %s
                """,
                (crop_id, state, district),
            )
        else:
            cur.execute(
                """
                SELECT crs.*, c.name as crop_name
                FROM crop_regional_suitability crs
                JOIN crops c ON crs.crop_id = c.id
                JOIN states s ON crs.state_id = s.id
                WHERE crs.crop_id = %s AND s.name = %s
                """,
                (crop_id, state),
            )
        return cur.fetchone()
    except Exception as e:
        logger.error(f"Error getting crop regional suitability: {e}")
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def insert_crop_regional_suitability(
    crop_id: int,
    state: str,
    district: str = None,
    suitability_score: int = 0,
    notes: str = None,
) -> Optional[int]:
    """
    Insert or update regional suitability for a crop.

    Args:
        crop_id: Crop ID
        state: State name
        district: District name (optional)
        suitability_score: Suitability score 0-100
        notes: Optional notes

    Returns:
        Inserted row ID or None
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()

        # First get state_id and district_id
        cur.execute(
            "SELECT id FROM states WHERE name = %s AND is_active = 1",
            (state,),
        )
        state_row = cur.fetchone()
        if not state_row:
            return None
        state_id = state_row[0]

        district_id = None
        if district:
            cur.execute(
                "SELECT id FROM districts WHERE name = %s AND state_id = %s AND is_active = 1",
                (district, state_id),
            )
            district_row = cur.fetchone()
            if district_row:
                district_id = district_row[0]

        cur.execute(
            """
            INSERT INTO crop_regional_suitability (crop_id, state_id, district_id, suitability_score, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE suitability_score = VALUES(suitability_score), notes = VALUES(notes), updated_at = CURRENT_TIMESTAMP
            """,
            (crop_id, state_id, district_id, suitability_score, notes),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"Error inserting regional suitability: {e}")
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def insert_crop(
    name: str,
    hindi_name: str,
    season: str,
    soil_type: str,
    soil_ph: str,
    n_value: int,
    p_value: int,
    k_value: int,
    irrigation: str,
    crop_type: str,
    description: str,
    region_desc: str,
    growth_duration: int,
    state_name: str,
    district_name: str,
    region_name: str,
    suitability_score: int,
    ml_probability: int,
    confidence: str,
    source: str = 'ml_engine',
) -> Optional[int]:
    """
    Insert a new crop recommendation result.

    Args:
        crop_id: Crop ID
        user_id: User ID
        state: State name
        district: District name
        season: Season
        soil_type: Soil type
        soil_ph: Soil pH
        n_value: Nitrogen value
        p_value: Phosphorus value
        k_value: Potassium value
        irrigation: Irrigation type
        overall_score: Overall suitability score
        soil_score: Soil compatibility score
        season_score: Season compatibility score
        region_score: Regional compatibility score
        irrigation_score: Irrigation compatibility score
        humidity_score: Humidity score
        wind_score: Wind score
        temperature_score: Temperature score
        rainfall_score: Rainfall score
        weather_data: Weather data as dict

    Returns:
        ID of inserted record or None on failure
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor()
        import json as json_module

        cur.execute(
            """
            INSERT INTO crop_recommendation_history (
                crop_id, user_id, state, district, season,
                soil_type, soil_ph, n_value, p_value, k_value,
                irrigation, overall_score, soil_score, season_score,
                region_score, irrigation_score, humidity_score,
                wind_score, temperature_score, rainfall_score,
                weather_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                crop_id, user_id, state, district, season,
                soil_type, soil_ph, n_value, p_value, k_value,
                irrigation, overall_score, soil_score, season_score,
                region_score, irrigation_score, humidity_score,
                wind_score, temperature_score, rainfall_score,
                json_module.dumps(weather_data) if weather_data else None,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"Failed to save crop recommendation: {e}")
        return None
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_crop_recommendation_history(
    user_id: int,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Get recommendation history for a user.

    Args:
        user_id: User ID
        limit: Maximum number of records

    Returns:
        List of history dictionaries
    """
    conn = None
    cur = None
    try:
        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT h.*, c.name as crop_name
            FROM crop_suitability_history h
            LEFT JOIN crops c ON h.crop_id = c.id
            WHERE h.user_id = %s
            ORDER BY h.analysis_date DESC
            LIMIT %s
            """,
            (user_id, limit),
        )
        return cur.fetchall() or []
    except Exception as e:
        logger.error(f"Error getting recommendation history: {e}")
        return []
    finally:
        if cur is not None:
            try:
                cur.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass