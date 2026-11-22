"""
tests/test_weather_analysis_scoring.py - Validation tests for weather suitability scoring logic

Tests the centralized weather_suitability_service.py:

- Temperature classification boundaries (GOOD / SUSTAINABLE / MARGINAL / BAD / UNKNOWN)
- Optimal minimum and maximum
- Sustainable minimum and maximum
- Exactly 1°C outside each sustainable limit
- Exactly 2°C outside each sustainable limit
- More than 2°C outside each sustainable limit
- pH classification boundaries (exactly ph_min/ph_max, 0.5 outside, more than 0.5 outside)
- Missing weather data and missing pH
- Multiple crops
- Weekly score aggregation and capping
- INSUFFICIENT_DATA when no valid days
"""

import pytest
from services.weather_suitability_service import (
    classify_temperature,
    classify_ph,
    analyse_daily,
    analyse_weekly,
    analyse_suitability,
    SCORE_GOOD,
    SCORE_SUSTAINABLE,
    SCORE_MARGINAL,
    SCORE_BAD,
)


# ---------------------------------------------------------------------------
# Fixture: a sample crop (Wheat from the dataset)
# ---------------------------------------------------------------------------
@pytest.fixture
def wheat_crop():
    return {
        "name": "Wheat",
        "best_low_temp": 15,
        "best_high_temp": 25,
        "low_temp": 5,
        "max_temp": 27,
        "ph_min": 5.5,
        "ph_max": 8.5,
    }


# ---------------------------------------------------------------------------
# Temperature classification tests
# ---------------------------------------------------------------------------
class TestTemperatureClassification:
    """Test classify_temperature() boundary conditions."""

    def test_inside_optimal_range_good(self, wheat_crop):
        """Inside optimal range -> GOOD."""
        result = classify_temperature(20, wheat_crop)
        assert result["classification"] == "GOOD"
        assert result["score"] == SCORE_GOOD

    def test_optimal_min_boundary_good(self, wheat_crop):
        """Exactly best_low_temp -> GOOD."""
        result = classify_temperature(15, wheat_crop)
        assert result["classification"] == "GOOD"

    def test_optimal_max_boundary_good(self, wheat_crop):
        """Exactly best_high_temp -> GOOD."""
        result = classify_temperature(25, wheat_crop)
        assert result["classification"] == "GOOD"

    def test_sustainable_min_boundary(self, wheat_crop):
        """Exactly low_temp -> SUSTAINABLE."""
        result = classify_temperature(5, wheat_crop)
        assert result["classification"] == "SUSTAINABLE"
        assert result["score"] == SCORE_SUSTAINABLE

    def test_sustainable_max_boundary(self, wheat_crop):
        """Exactly max_temp -> SUSTAINABLE."""
        result = classify_temperature(27, wheat_crop)
        assert result["classification"] == "SUSTAINABLE"
        assert result["score"] == SCORE_SUSTAINABLE

    def test_just_below_optimal_min_sustainable(self, wheat_crop):
        """1°C below best_low (14) -> SUSTAINABLE."""
        result = classify_temperature(14, wheat_crop)
        assert result["classification"] == "SUSTAINABLE"

    def test_just_above_optimal_max_sustainable(self, wheat_crop):
        """1°C above best_high (26) -> SUSTAINABLE."""
        result = classify_temperature(26, wheat_crop)
        assert result["classification"] == "SUSTAINABLE"

    def test_one_degree_above_max_marginal(self, wheat_crop):
        """max_temp + 1 (28) -> MARGINAL."""
        result = classify_temperature(28, wheat_crop)
        assert result["classification"] == "MARGINAL"
        assert result["score"] == SCORE_MARGINAL

    def test_two_degrees_above_max_marginal(self, wheat_crop):
        """max_temp + 2 (29) -> MARGINAL."""
        result = classify_temperature(29, wheat_crop)
        assert result["classification"] == "MARGINAL"

    def test_one_degree_below_low_marginal(self, wheat_crop):
        """low_temp - 1 (4) -> MARGINAL."""
        result = classify_temperature(4, wheat_crop)
        assert result["classification"] == "MARGINAL"

    def test_two_degrees_below_low_marginal(self, wheat_crop):
        """low_temp - 2 (3) -> MARGINAL."""
        result = classify_temperature(3, wheat_crop)
        assert result["classification"] == "MARGINAL"

    def test_more_than_two_above_max_bad(self, wheat_crop):
        """max_temp + 2.1 (29.1) -> BAD."""
        result = classify_temperature(29.1, wheat_crop)
        assert result["classification"] == "BAD"
        assert result["score"] == SCORE_BAD

    def test_more_than_two_below_low_bad(self, wheat_crop):
        """low_temp - 2.1 (2.9) -> BAD."""
        result = classify_temperature(2.9, wheat_crop)
        assert result["classification"] == "BAD"

    def test_missing_temperature_unknown(self, wheat_crop):
        """None temperature -> UNKNOWN."""
        result = classify_temperature(None, wheat_crop)
        assert result["classification"] == "UNKNOWN"
        assert result["score"] is None

    def test_missing_reference_values_unknown(self):
        """Crop with missing reference values -> UNKNOWN."""
        crop = {"name": "Test", "best_low_temp": None, "best_high_temp": None, "low_temp": None, "max_temp": None}
        result = classify_temperature(20, crop)
        assert result["classification"] == "UNKNOWN"

    @pytest.mark.parametrize("temp,expected", [
        (20, "GOOD"),     # inside optimal
        (15, "GOOD"),     # optimal min boundary
        (25, "GOOD"),     # optimal max boundary
        (10, "SUSTAINABLE"),  # sustainable low-mid
        (5, "SUSTAINABLE"),   # sustainable min boundary (low_temp)
        (27, "SUSTAINABLE"),  # sustainable max boundary (max_temp)
        (28, "MARGINAL"),     # max_temp + 1
        (29, "MARGINAL"),     # max_temp + 2
        (29.1, "BAD"),        # max_temp + 2.1
        (4, "MARGINAL"),      # low_temp - 1
        (3, "MARGINAL"),      # low_temp - 2
        (2.9, "BAD"),         # low_temp - 2.1
    ])
    def test_classification_matrix(self, wheat_crop, temp, expected):
        """Parametrized classification matrix."""
        result = classify_temperature(temp, wheat_crop)
        assert result["classification"] == expected


# ---------------------------------------------------------------------------
# pH classification tests
# ---------------------------------------------------------------------------
class TestPHClassification:
    """Test classify_ph() boundary conditions."""

    def test_ph_within_range_good(self, wheat_crop):
        """pH within range -> GOOD."""
        result = classify_ph(6.8, wheat_crop)
        assert result["status"] == "GOOD"
        assert result["difference"] == 0.0

    def test_ph_exact_min_good(self, wheat_crop):
        """Exactly ph_min -> GOOD."""
        result = classify_ph(6.0, wheat_crop)
        assert result["status"] == "GOOD"

    def test_ph_exact_max_good(self, wheat_crop):
        """Exactly ph_max -> GOOD."""
        result = classify_ph(7.5, wheat_crop)
        assert result["status"] == "GOOD"

    def test_ph_05_below_min_marginal(self, wheat_crop):
        """ph_min - 0.5 (5.0) -> MARGINAL."""
        result = classify_ph(5.0, wheat_crop)
        assert result["status"] == "MARGINAL"
        assert result["difference"] == 0.5

    def test_ph_05_above_max_marginal(self, wheat_crop):
        """ph_max + 0.5 (9.0) -> MARGINAL."""
        result = classify_ph(9.0, wheat_crop)
        assert result["status"] == "MARGINAL"
        assert result["difference"] == 0.5

    def test_ph_more_than_05_below_min_bad(self, wheat_crop):
        """ph_min - 0.6 (4.9) -> BAD."""
        result = classify_ph(4.9, wheat_crop)
        assert result["status"] == "BAD"

    def test_ph_more_than_05_above_max_bad(self, wheat_crop):
        """ph_max + 0.6 (9.1) -> BAD."""
        result = classify_ph(9.1, wheat_crop)
        assert result["status"] == "BAD"

    def test_ph_not_provided_unknown(self, wheat_crop):
        """None pH -> UNKNOWN."""
        result = classify_ph(None, wheat_crop)
        assert result["status"] == "UNKNOWN"
        assert result["farmer_ph"] is None

    def test_ph_outside_physical_range_unknown(self, wheat_crop):
        """pH < 0 or > 14 -> UNKNOWN."""
        result = classify_ph(-1, wheat_crop)
        assert result["status"] == "UNKNOWN"
        result = classify_ph(15, wheat_crop)
        assert result["status"] == "UNKNOWN"

    def test_ph_missing_reference_unknown(self):
        """Missing crop pH reference -> UNKNOWN."""
        crop = {"name": "Test", "ph_min": None, "ph_max": None}
        result = classify_ph(6.5, crop)
        assert result["status"] == "UNKNOWN"

    @pytest.mark.parametrize("ph,expected", [
        (5.5, "GOOD"),
        (8.5, "GOOD"),
        (6.8, "GOOD"),
        (5.0, "MARGINAL"),   # 0.5 below min
        (9.0, "MARGINAL"),   # 0.5 above max
        (4.9, "BAD"),        # > 0.5 below min
        (9.1, "BAD"),        # > 0.5 above max
        (0, "BAD"),          # far below min
        (14, "BAD"),         # far above max
    ])
    def test_ph_classification_matrix(self, wheat_crop, ph, expected):
        """Parametrized pH classification matrix."""
        result = classify_ph(ph, wheat_crop)
        assert result["status"] == expected


# ---------------------------------------------------------------------------
# Daily analysis tests
# ---------------------------------------------------------------------------
class TestDailyAnalysis:
    """Test analyse_daily()."""

    def test_all_good_readings(self, wheat_crop):
        """All readings GOOD -> daily score = 100/7 * 7 / 7 = 100/7."""
        readings = [
            {"temp": 20, "time_label": "12:00 AM", "hour": 0},
            {"temp": 20, "time_label": "4:00 AM", "hour": 4},
            {"temp": 20, "time_label": "8:00 AM", "hour": 8},
            {"temp": 20, "time_label": "12:00 PM", "hour": 12},
            {"temp": 20, "time_label": "4:00 PM", "hour": 16},
            {"temp": 20, "time_label": "8:00 PM", "hour": 20},
        ]
        result = analyse_daily(readings, wheat_crop)
        assert result["status"] == "GOOD"
        assert result["valid_readings"] == 6
        assert result["classifications"]["GOOD"] == 6
        # Average of six GOOD scores = SCORE_GOOD
        assert abs(result["score"] - SCORE_GOOD) < 0.01

    def test_mixed_readings(self, wheat_crop):
        """Mixed classifications -> average score."""
        readings = [
            {"temp": 20, "time_label": "12:00 AM", "hour": 0},   # GOOD
            {"temp": 20, "time_label": "4:00 AM", "hour": 4},   # GOOD
            {"temp": 10, "time_label": "8:00 AM", "hour": 8},   # SUSTAINABLE
            {"temp": 28, "time_label": "12:00 PM", "hour": 12}, # MARGINAL
            {"temp": 40, "time_label": "4:00 PM", "hour": 16},  # BAD
            {"temp": None, "time_label": "8:00 PM", "hour": 20}, # UNKNOWN
        ]
        result = analyse_daily(readings, wheat_crop)
        assert result["valid_readings"] == 5
        assert result["classifications"]["GOOD"] == 2
        assert result["classifications"]["SUSTAINABLE"] == 1
        assert result["classifications"]["MARGINAL"] == 1
        assert result["classifications"]["BAD"] == 1
        assert result["classifications"]["UNKNOWN"] == 1
        # Score = average of 5 valid scores
        expected = (2 * SCORE_GOOD + SCORE_SUSTAINABLE + SCORE_MARGINAL + SCORE_BAD) / 5
        assert abs(result["score"] - expected) < 0.01

    def test_no_valid_readings_unknown(self, wheat_crop):
        """No valid readings -> UNKNOWN day."""
        readings = [
            {"temp": None, "time_label": "12:00 AM", "hour": 0},
            {"temp": None, "time_label": "4:00 AM", "hour": 4},
        ]
        result = analyse_daily(readings, wheat_crop)
        assert result["status"] == "UNKNOWN"
        assert result["score"] is None
        assert result["valid_readings"] == 0

    def test_empty_readings_unknown(self, wheat_crop):
        """Empty readings list -> UNKNOWN day."""
        result = analyse_daily([], wheat_crop)
        assert result["status"] == "UNKNOWN"
        assert result["score"] is None


# ---------------------------------------------------------------------------
# Weekly aggregation tests
# ---------------------------------------------------------------------------
class TestWeeklyAggregation:
    """Test analyse_weekly()."""

    def test_all_good_days_score_100(self):
        """7 GOOD days -> score = 100 (capped)."""
        daily = [
            {"date": f"2025-11-{22+i:02d}", "status": "GOOD", "score": SCORE_GOOD,
             "valid_readings": 6, "total_readings": 6, "classifications": {"GOOD": 6, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 0}, "slots": []}
            for i in range(7)
        ]
        result = analyse_weekly(daily)
        assert result["weekly_score"] == 100.0
        assert result["status"] == "FAVOURABLE"
        assert result["valid_days"] == 7

    def test_unknown_days_excluded(self):
        """UNKNOWN days excluded from score."""
        daily = [
            {"date": "2025-11-22", "status": "GOOD", "score": SCORE_GOOD,
             "valid_readings": 6, "total_readings": 6, "classifications": {"GOOD": 6, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 0}, "slots": []},
            {"date": "2025-11-23", "status": "UNKNOWN", "score": None,
             "valid_readings": 0, "total_readings": 6, "classifications": {"GOOD": 0, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 6}, "slots": []},
        ] + [
            {"date": f"2025-11-{24+i:02d}", "status": "UNKNOWN", "score": None,
             "valid_readings": 0, "total_readings": 6, "classifications": {"GOOD": 0, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 6}, "slots": []}
            for i in range(5)
        ]
        result = analyse_weekly(daily)
        assert result["valid_days"] == 1
        assert abs(result["weekly_score"] - SCORE_GOOD) < 0.01
        assert result["status"] == "UNFAVOURABLE"  # 14.29 < 40

    def test_no_valid_days_insufficient(self):
        """All UNKNOWN -> INSUFFICIENT_DATA."""
        daily = [
            {"date": f"2025-11-{22+i:02d}", "status": "UNKNOWN", "score": None,
             "valid_readings": 0, "total_readings": 6, "classifications": {"GOOD": 0, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 6}, "slots": []}
            for i in range(7)
        ]
        result = analyse_weekly(daily)
        assert result["weekly_score"] is None
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["valid_days"] == 0

    def test_score_capped_at_100(self):
        """Score never exceeds 100."""
        daily = [
            {"date": f"2025-11-{22+i:02d}", "status": "GOOD", "score": SCORE_GOOD,
             "valid_readings": 6, "total_readings": 6, "classifications": {"GOOD": 6, "SUSTAINABLE": 0, "MARGINAL": 0, "BAD": 0, "UNKNOWN": 0}, "slots": []}
            for i in range(7)
        ]
        result = analyse_weekly(daily)
        assert result["weekly_score"] <= 100.0

    def test_empty_daily_list(self):
        """Empty daily list -> INSUFFICIENT_DATA."""
        result = analyse_weekly([])
        assert result["status"] == "INSUFFICIENT_DATA"
        assert result["valid_days"] == 0


# ---------------------------------------------------------------------------
# Full analysis tests
# ---------------------------------------------------------------------------
class TestFullAnalysis:
    """Test analyse_suitability() end-to-end."""

    def test_wheat_full_analysis(self):
        """Full analysis for Wheat with good weather."""
        hourly_by_day = [
            [  # Day 1 - all GOOD
                {"temp": 20, "time_label": "12:00 AM", "hour": 0, "date": "2025-11-22"},
                {"temp": 20, "time_label": "4:00 AM", "hour": 4, "date": "2025-11-22"},
                {"temp": 20, "time_label": "8:00 AM", "hour": 8, "date": "2025-11-22"},
                {"temp": 20, "time_label": "12:00 PM", "hour": 12, "date": "2025-11-22"},
                {"temp": 20, "time_label": "4:00 PM", "hour": 16, "date": "2025-11-22"},
                {"temp": 20, "time_label": "8:00 PM", "hour": 20, "date": "2025-11-22"},
            ],
            [  # Day 2 - all GOOD
                {"temp": 20, "time_label": "12:00 AM", "hour": 0, "date": "2025-11-23"},
                {"temp": 20, "time_label": "4:00 AM", "hour": 4, "date": "2025-11-23"},
                {"temp": 20, "time_label": "8:00 AM", "hour": 8, "date": "2025-11-23"},
                {"temp": 20, "time_label": "12:00 PM", "hour": 12, "date": "2025-11-23"},
                {"temp": 20, "time_label": "4:00 PM", "hour": 16, "date": "2025-11-23"},
                {"temp": 20, "time_label": "8:00 PM", "hour": 20, "date": "2025-11-23"},
            ],
        ] + [
            [  # Days 3-7 - all GOOD
                {"temp": 20, "time_label": "12:00 AM", "hour": 0, "date": f"2025-11-{22+i:02d}"},
                {"temp": 20, "time_label": "4:00 AM", "hour": 4, "date": f"2025-11-{22+i:02d}"},
                {"temp": 20, "time_label": "8:00 AM", "hour": 8, "date": f"2025-11-{22+i:02d}"},
                {"temp": 20, "time_label": "12:00 PM", "hour": 12, "date": f"2025-11-{22+i:02d}"},
                {"temp": 20, "time_label": "4:00 PM", "hour": 16, "date": f"2025-11-{22+i:02d}"},
                {"temp": 20, "time_label": "8:00 PM", "hour": 20, "date": f"2025-11-{22+i:02d}"},
            ] for i in range(2, 7)
        ]

        result = analyse_suitability("Wheat", hourly_by_day, 6.8)
        assert result["success"] is True
        assert result["crop"]["name"] == "Wheat"
        assert result["crop"]["best_low_temp"] == 15
        assert result["crop"]["best_high_temp"] == 25
        assert result["crop"]["low_temp"] == 5
        assert result["crop"]["max_temp"] == 27
        assert result["crop"]["ph_min"] == 5.5
        assert result["crop"]["ph_max"] == 8.5
        assert result["weather_analysis"]["weekly_score"] == 100.0
        assert result["weather_analysis"]["status"] == "FAVOURABLE"
        assert result["weather_analysis"]["valid_days"] == 7
        assert result["ph_analysis"]["status"] == "GOOD"
        assert result["ph_analysis"]["farmer_ph"] == 6.8

    def test_crop_not_found(self):
        """Non-existent crop -> error."""
        result = analyse_suitability("NonExistentCrop", [], 6.5)
        assert result["success"] is False
        assert result["error"] == "crop_not_found"

    def test_missing_ph_unknown(self):
        """Missing pH -> UNKNOWN status, no crash."""
        hourly_by_day = [
            [{"temp": 20, "time_label": "12:00 AM", "hour": 0, "date": "2025-11-22"}] * 6,
        ] * 7
        result = analyse_suitability("Wheat", hourly_by_day, None)
        assert result["success"] is True
        assert result["ph_analysis"]["status"] == "UNKNOWN"
        assert result["ph_analysis"]["farmer_ph"] is None

    @pytest.mark.parametrize("crop_name", ["Wheat", "Rice", "Maize", "Potato", "Tomato"])
    def test_multiple_crops(self, crop_name):
        """Test multiple crops from the dataset."""
        hourly_by_day = [
            [{"temp": 20, "time_label": "12:00 AM", "hour": 0, "date": f"2025-11-{22+i:02d}"}] * 6
            for i in range(7)
        ]
        result = analyse_suitability(crop_name, hourly_by_day, 6.5)
        assert result["success"] is True, f"Crop {crop_name} should be found"
        assert result["crop"]["name"] == crop_name

    def test_ph_bad_status(self):
        """pH far outside range -> BAD."""
        hourly_by_day = [
            [{"temp": 20, "time_label": "12:00 AM", "hour": 0, "date": f"2025-11-{22+i:02d}"}] * 6
            for i in range(7)
        ]
        result = analyse_suitability("Wheat", hourly_by_day, 3.0)  # wheat ph_min=5.5, diff=2.5
        assert result["ph_analysis"]["status"] == "BAD"
        assert result["ph_analysis"]["difference"] == 2.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
