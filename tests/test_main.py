"""Unit tests for GeoDataProcessor."""
import pytest
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, "/Users/johndoe/projects/geological-data-processor")
from src.main import GeoDataProcessor


@pytest.fixture
def assay_df():
    return pd.DataFrame({
        "hole_id": ["BH001"] * 5 + ["BH002"] * 4,
        "from_m": [0, 1, 2, 3, 4, 0, 1.5, 3, 4.5],
        "to_m": [1, 2, 3, 4, 5, 1.5, 3, 4.5, 6],
        "grade_pct": [0.15, 0.82, 1.45, 0.63, 0.28, 0.05, 1.12, 2.30, 0.41],
    })


@pytest.fixture
def proc():
    return GeoDataProcessor(config={"density_t_m3": 1.75, "cutoff_grade": 0.3})


class TestValidation:
    def test_empty_raises(self, proc):
        with pytest.raises(ValueError, match="empty"):
            proc.validate(pd.DataFrame())

    def test_overlapping_intervals_raises(self, proc):
        df = pd.DataFrame({"from_m": [2, 0], "to_m": [1, 3], "grade_pct": [0.5, 0.8]})
        with pytest.raises(ValueError, match="from_m >= to_m"):
            proc.validate(df)

    def test_valid_data_passes(self, proc, assay_df):
        assert proc.validate(assay_df) is True


class TestPreprocess:
    def test_interval_calculated(self, proc, assay_df):
        result = proc.preprocess(assay_df)
        assert "interval_m" in result.columns
        assert (result["interval_m"] > 0).all()

    def test_column_normalized(self, proc):
        df = pd.DataFrame({"HOLE ID": ["X"], "From M": [0], "To M": [1], "Grade PCT": [0.5]})
        result = proc.preprocess(df)
        assert "hole_id" in result.columns
        assert "grade_pct" in result.columns


class TestEstimateResources:
    def test_returns_expected_keys(self, proc, assay_df):
        result = proc.estimate_resources(assay_df, cutoff_grade=0.0)
        assert "total_tonnes" in result
        assert "mean_grade" in result
        assert "metal_quantity" in result
        assert "grade_distribution" in result

    def test_cutoff_filters_intervals(self, proc, assay_df):
        res_no_cutoff = proc.estimate_resources(assay_df, cutoff_grade=0.0)
        res_with_cutoff = proc.estimate_resources(assay_df, cutoff_grade=0.5)
        assert res_with_cutoff["above_cutoff_intervals"] < res_no_cutoff["above_cutoff_intervals"]

    def test_mean_grade_above_cutoff(self, proc, assay_df):
        cutoff = 0.3
        result = proc.estimate_resources(assay_df, cutoff_grade=cutoff)
        assert result["mean_grade"] >= cutoff

    def test_metal_quantity_positive(self, proc, assay_df):
        result = proc.estimate_resources(assay_df, cutoff_grade=0.0)
        assert result["metal_quantity"] > 0

    def test_missing_grade_col_raises(self, proc):
        df = pd.DataFrame({"hole_id": ["A"], "from_m": [0], "to_m": [1], "value": [0.5]})
        with pytest.raises(ValueError):
            proc.estimate_resources(df, grade_col="grade_pct")

    def test_auto_detect_grade_column(self, proc):
        df = pd.DataFrame({
            "hole_id": ["A", "A"],
            "from_m": [0, 1],
            "to_m": [1, 2],
            "grade_au_gt": [1.2, 0.8],
        })
        result = proc.estimate_resources(df, grade_col="grade_au_gt")
        assert result["total_tonnes"] > 0


class TestCompositeIntervals:
    def test_returns_dataframe(self, proc, assay_df):
        result = proc.composite_intervals(assay_df, composite_length_m=2.0)
        assert isinstance(result, pd.DataFrame)

    def test_composite_grade_within_range(self, proc, assay_df):
        result = proc.composite_intervals(assay_df, composite_length_m=2.0)
        min_grade = assay_df["grade_pct"].min()
        max_grade = assay_df["grade_pct"].max()
        assert result["composite_grade_pct"].between(min_grade, max_grade).all()


class TestAnalyze:
    def test_analyze_returns_stats(self, proc, assay_df):
        result = proc.analyze(assay_df)
        assert result["total_records"] == 9
        assert "summary_stats" in result
