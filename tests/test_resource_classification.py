"""
Unit tests for JORC resource classification and tonnage estimation.
"""
import pytest
import pandas as pd
from src.main import GeologicalDataProcessor


@pytest.fixture
def processor():
    return GeologicalDataProcessor()


@pytest.fixture
def sample_df():
    return pd.DataFrame({
        "hole_id": ["BH-001"] * 5 + ["BH-002"] * 5 + ["BH-003"] * 5 + ["BH-004"] * 5,
        "from_m": [0, 5, 10, 15, 20] * 4,
        "to_m": [5, 10, 15, 20, 25] * 4,
        "interval_m": [5.0] * 20,
        "grade": [75.2, 74.8, 76.1, 75.5, 74.9,
                  73.0, 74.2, 75.0, 73.8, 74.6,
                  76.5, 75.8, 76.0, 75.3, 76.2,
                  74.1, 73.9, 74.5, 74.8, 75.0],
    })


class TestResourceClassification:

    def test_measured_classification(self, processor, sample_df):
        """Tight spacing with sufficient samples → Measured."""
        result = processor.classify_resource_confidence(sample_df, drill_spacing_m=20.0)
        assert result["jorc_classification"] == "Measured"
        assert result["confidence_score"] >= 70

    def test_indicated_classification(self, processor, sample_df):
        """Moderate spacing → Indicated."""
        result = processor.classify_resource_confidence(sample_df, drill_spacing_m=60.0)
        assert result["jorc_classification"] == "Indicated"

    def test_inferred_classification(self, processor, sample_df):
        """Wide spacing → Inferred."""
        result = processor.classify_resource_confidence(sample_df, drill_spacing_m=200.0)
        assert result["jorc_classification"] == "Inferred"

    def test_invalid_drill_spacing_raises(self, processor, sample_df):
        with pytest.raises(ValueError, match="drill_spacing_m must be positive"):
            processor.classify_resource_confidence(sample_df, drill_spacing_m=0.0)

    def test_empty_dataframe_raises(self, processor):
        with pytest.raises(ValueError, match="DataFrame cannot be empty"):
            processor.classify_resource_confidence(pd.DataFrame(), drill_spacing_m=50.0)

    def test_returns_required_keys(self, processor, sample_df):
        result = processor.classify_resource_confidence(sample_df, drill_spacing_m=50.0)
        for key in ("jorc_classification", "confidence_score", "sample_count",
                    "reporting_standard", "classification_rationale"):
            assert key in result


class TestTonnageEstimation:

    def test_basic_tonnage(self, processor, sample_df):
        result = processor.estimate_tonnage(sample_df, area_sqm=1_000_000, avg_thickness_m=5.0)
        assert result["in_situ_tonnes"] == pytest.approx(6_750_000, rel=0.01)

    def test_invalid_area_raises(self, processor, sample_df):
        with pytest.raises(ValueError, match="area_sqm must be positive"):
            processor.estimate_tonnage(sample_df, area_sqm=0, avg_thickness_m=5.0)

    def test_invalid_thickness_raises(self, processor, sample_df):
        with pytest.raises(ValueError, match="avg_thickness_m must be positive"):
            processor.estimate_tonnage(sample_df, area_sqm=500_000, avg_thickness_m=-1.0)

    def test_custom_bulk_density(self, processor, sample_df):
        result_coal = processor.estimate_tonnage(
            sample_df, area_sqm=100_000, avg_thickness_m=4.0, bulk_density_t_m3=1.35
        )
        result_rock = processor.estimate_tonnage(
            sample_df, area_sqm=100_000, avg_thickness_m=4.0, bulk_density_t_m3=2.7
        )
        assert result_rock["in_situ_tonnes"] == pytest.approx(
            result_coal["in_situ_tonnes"] * 2, rel=0.01
        )

    def test_grade_column_calculates_contained(self, processor, sample_df):
        result = processor.estimate_tonnage(
            sample_df, area_sqm=100_000, avg_thickness_m=4.0, grade_column="grade"
        )
        assert result["contained_tonnes"] is not None
        assert result["avg_grade_pct"] is not None
        assert 70 < result["avg_grade_pct"] < 80
