"""
Unit tests for GradeOutlierDetector.
"""

import pandas as pd
import pytest
from src.grade_outlier_detector import GradeOutlierDetector, GradeOutlierReport, OutlierFlag


def make_assay_df(with_outlier: bool = True):
    """Create a small assay DataFrame."""
    grades = [0.35, 0.42, 0.38, 0.40, 0.36, 0.39, 0.41, 0.37, 0.43, 0.38]
    if with_outlier:
        grades.append(5.80)  # obvious high-grade outlier
    n = len(grades)
    return pd.DataFrame({
        "hole_id":   [f"DDH-{i:03d}" for i in range(n)],
        "from_m":    [i * 2.0 for i in range(n)],
        "to_m":      [(i + 1) * 2.0 for i in range(n)],
        "grade_pct": grades,
    })


@pytest.fixture
def detector():
    return GradeOutlierDetector(method="modified_zscore", zscore_threshold=3.5)


class TestInit:
    def test_invalid_method_raises(self):
        with pytest.raises(ValueError, match="method must be one of"):
            GradeOutlierDetector(method="invalid")

    def test_zero_iqr_multiplier_raises(self):
        with pytest.raises(ValueError, match="iqr_multiplier"):
            GradeOutlierDetector(method="iqr", iqr_multiplier=0)

    def test_default_method_is_modified_zscore(self):
        d = GradeOutlierDetector()
        assert d.method == "modified_zscore"


class TestDetect:
    def test_returns_report(self, detector):
        report = detector.detect(make_assay_df())
        assert isinstance(report, GradeOutlierReport)

    def test_detects_high_grade_outlier(self, detector):
        report = detector.detect(make_assay_df(with_outlier=True))
        assert report.n_high_outliers >= 1

    def test_no_outliers_in_clean_data(self, detector):
        report = detector.detect(make_assay_df(with_outlier=False))
        assert report.n_high_outliers == 0

    def test_outlier_pct_calculated(self, detector):
        report = detector.detect(make_assay_df(with_outlier=True))
        assert 0 < report.outlier_pct <= 100

    def test_statistics_keys_present(self, detector):
        report = detector.detect(make_assay_df())
        assert set(["mean", "median", "p90", "p99"]).issubset(report.statistics.keys())

    def test_missing_grade_column_raises(self, detector):
        df = make_assay_df().drop(columns=["grade_pct"])
        with pytest.raises(ValueError, match="not found"):
            detector.detect(df, grade_column="grade_pct")

    def test_all_null_grades_raises(self, detector):
        df = make_assay_df()
        df["grade_pct"] = None
        with pytest.raises(ValueError, match="null"):
            detector.detect(df)

    def test_too_few_valid_grades_raises(self, detector):
        df = pd.DataFrame({
            "hole_id": ["A", "B"],
            "from_m": [0, 2],
            "to_m": [2, 4],
            "grade_pct": [0.5, 0.6],
        })
        with pytest.raises(ValueError, match="At least 4"):
            detector.detect(df)


class TestIQRMethod:
    def test_iqr_detects_outlier(self):
        d = GradeOutlierDetector(method="iqr", iqr_multiplier=1.5)
        report = d.detect(make_assay_df(with_outlier=True))
        assert report.n_high_outliers >= 1


class TestLognormalMethod:
    def test_lognormal_detects_outlier(self):
        d = GradeOutlierDetector(method="lognormal", lognormal_sigma=2.5)
        report = d.detect(make_assay_df(with_outlier=True))
        assert report.n_high_outliers >= 1


class TestTopOutliers:
    def test_returns_n_items(self, detector):
        report = detector.detect(make_assay_df(with_outlier=True))
        tops = detector.top_outliers(report, n=1, flag_type="high")
        assert len(tops) <= 1

    def test_sorted_highest_first(self, detector):
        report = detector.detect(make_assay_df(with_outlier=True))
        tops = detector.top_outliers(report, flag_type="high")
        grades = [f.grade for f in tops]
        assert grades == sorted(grades, reverse=True)

    def test_invalid_flag_type_raises(self, detector):
        report = detector.detect(make_assay_df())
        with pytest.raises(ValueError, match="flag_type"):
            detector.top_outliers(report, flag_type="medium")


class TestOutlierFlag:
    def test_flag_has_correct_type(self, detector):
        report = detector.detect(make_assay_df(with_outlier=True))
        high_flags = [f for f in report.flags if f.flag_type == "high"]
        assert all(isinstance(f, OutlierFlag) for f in high_flags)

    def test_flag_grade_matches_outlier(self, detector):
        report = detector.detect(make_assay_df(with_outlier=True))
        high_flags = [f for f in report.flags if f.flag_type == "high"]
        assert any(f.grade > 5.0 for f in high_flags)
