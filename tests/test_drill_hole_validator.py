"""
Unit tests for drill hole collar and assay validation module.
"""

import pytest
from src.drill_hole_validator import (
    CollarRecord,
    AssayInterval,
    ValidationIssue,
    DrillHoleValidator,
)


# ---------------------------------------------------------------------------
# CollarRecord tests
# ---------------------------------------------------------------------------


class TestCollarRecord:
    def test_valid_creation(self):
        c = CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, -60, 270, "DD")
        assert c.hole_id == "DDH-001"

    def test_empty_id_raises(self):
        with pytest.raises(ValueError, match="hole_id cannot be empty"):
            CollarRecord("  ", 355000, 9705000, 150.0, 300.0)

    def test_zero_td_raises(self):
        with pytest.raises(ValueError, match="total_depth_m must be positive"):
            CollarRecord("DDH-001", 355000, 9705000, 150.0, 0.0)

    def test_invalid_dip_raises(self):
        with pytest.raises(ValueError, match="dip_degrees"):
            CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, dip_degrees=-95.0)

    def test_invalid_azimuth_raises(self):
        with pytest.raises(ValueError, match="azimuth_degrees"):
            CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, azimuth_degrees=361.0)

    def test_invalid_hole_type_raises(self):
        with pytest.raises(ValueError, match="hole_type must be one of"):
            CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, hole_type="UNKNOWN")

    def test_azimuth_360_raises(self):
        """Azimuth 360 is invalid; should be 0."""
        with pytest.raises(ValueError, match="azimuth_degrees"):
            CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, azimuth_degrees=360.0)


# ---------------------------------------------------------------------------
# AssayInterval tests
# ---------------------------------------------------------------------------


class TestAssayInterval:
    def test_valid_creation(self):
        a = AssayInterval("DDH-001", 0.0, 1.0, 45.5, "%")
        assert a.interval_length_m == pytest.approx(1.0)

    def test_to_less_than_from_raises(self):
        with pytest.raises(ValueError, match="to_m.*must be greater than"):
            AssayInterval("DDH-001", 5.0, 3.0, 45.5)

    def test_equal_from_to_raises(self):
        with pytest.raises(ValueError):
            AssayInterval("DDH-001", 5.0, 5.0, 45.5)

    def test_negative_from_raises(self):
        with pytest.raises(ValueError, match="from_m cannot be negative"):
            AssayInterval("DDH-001", -1.0, 2.0, 45.5)

    def test_negative_grade_raises(self):
        with pytest.raises(ValueError, match="grade cannot be negative"):
            AssayInterval("DDH-001", 0.0, 1.0, -5.0)

    def test_interval_length(self):
        a = AssayInterval("DDH-001", 10.0, 13.5, 32.0)
        assert a.interval_length_m == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# DrillHoleValidator tests
# ---------------------------------------------------------------------------


@pytest.fixture
def boundary():
    return (350000, 360000, 9700000, 9710000)


@pytest.fixture
def validator(boundary):
    return DrillHoleValidator(project_boundary=boundary, max_grade_value=80.0)


@pytest.fixture
def good_collars():
    return [
        CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, -60, 180, "DD"),
        CollarRecord("DDH-002", 356000, 9706000, 148.5, 250.0, -70, 200, "DD"),
    ]


@pytest.fixture
def good_assays():
    return [
        AssayInterval("DDH-001", 0.0, 1.0, 45.0, "%"),
        AssayInterval("DDH-001", 1.0, 2.0, 55.0, "%"),
        AssayInterval("DDH-002", 0.0, 2.0, 30.0, "%"),
    ]


class TestDrillHoleValidator:
    def test_valid_no_issues(self, validator, good_collars, good_assays):
        issues = validator.validate_all(good_collars, good_assays)
        errors = [i for i in issues if i.severity == "ERROR"]
        assert len(errors) == 0

    def test_duplicate_collar_error(self, validator, good_collars):
        duplicate = CollarRecord("DDH-001", 355100, 9705100, 151.0, 200.0, -60, 180, "DD")
        issues = validator.validate_collars(good_collars + [duplicate])
        errors = [i for i in issues if i.category == "duplicate_id"]
        assert len(errors) >= 1

    def test_outside_boundary_warning(self, validator):
        collar = CollarRecord("DDH-OUT", 400000, 9705000, 150.0, 300.0, -60, 90, "DD")
        issues = validator.validate_collars([collar])
        warnings = [i for i in issues if i.category == "outside_boundary"]
        assert len(warnings) == 1

    def test_no_boundary_no_warning(self):
        v = DrillHoleValidator()
        collar = CollarRecord("DDH-001", 999999, 1, 0.0, 100.0, -60, 90, "DD")
        issues = v.validate_collars([collar])
        boundary_warnings = [i for i in issues if i.category == "outside_boundary"]
        assert len(boundary_warnings) == 0

    def test_depth_exceeded_error(self, validator, good_collars):
        bad_assay = AssayInterval("DDH-001", 295.0, 305.0, 40.0)  # TD = 300
        issues = validator.validate_assays([bad_assay], good_collars)
        errors = [i for i in issues if i.category == "depth_exceeded"]
        assert len(errors) == 1

    def test_interval_overlap_error(self, validator, good_collars):
        overlapping = [
            AssayInterval("DDH-001", 0.0, 5.0, 40.0),
            AssayInterval("DDH-001", 4.0, 8.0, 35.0),  # overlaps at 4-5m
        ]
        issues = validator.validate_assays(overlapping, good_collars)
        errors = [i for i in issues if i.category == "interval_overlap"]
        assert len(errors) >= 1

    def test_grade_outlier_warning(self, validator, good_collars):
        high_grade = [AssayInterval("DDH-001", 0.0, 1.0, 95.0, "%")]  # > max 80%
        issues = validator.validate_assays(high_grade, good_collars)
        warnings = [i for i in issues if i.category == "grade_outlier"]
        assert len(warnings) == 1

    def test_missing_collar_warning(self, validator, good_collars):
        orphan_assay = [AssayInterval("UNKNOWN-HOLE", 0.0, 2.0, 30.0)]
        issues = validator.validate_assays(orphan_assay, good_collars)
        warnings = [i for i in issues if i.category == "missing_collar"]
        assert len(warnings) == 1

    def test_long_interval_info(self, validator, good_collars):
        long_iv = [AssayInterval("DDH-001", 0.0, 60.0, 35.0)]  # 60m interval
        issues = validator.validate_assays(long_iv, good_collars)
        infos = [i for i in issues if i.category == "long_interval"]
        assert len(infos) == 1

    def test_summary_no_errors(self, validator, good_collars, good_assays):
        issues = validator.validate_all(good_collars, good_assays)
        summary = validator.summary(issues)
        assert summary["errors"] == 0
        assert summary["passes_jorc_qaqc"] is True

    def test_summary_with_errors(self, validator, good_collars):
        dup = CollarRecord("DDH-001", 355100, 9705100, 151.0, 200.0, -60, 180, "DD")
        issues = validator.validate_collars(good_collars + [dup])
        summary = validator.summary(issues)
        assert summary["errors"] >= 1
        assert summary["passes_jorc_qaqc"] is False

    def test_summary_keys(self, validator, good_collars, good_assays):
        issues = validator.validate_all(good_collars, good_assays)
        summary = validator.summary(issues)
        expected = {"total_issues", "errors", "warnings", "info",
                    "passes_jorc_qaqc", "categories", "affected_holes"}
        assert expected.issubset(summary.keys())

    def test_empty_collars_raises(self, validator):
        with pytest.raises(ValueError, match="collars list cannot be empty"):
            validator.validate_collars([])

    def test_invalid_boundary_raises(self):
        with pytest.raises(ValueError):
            DrillHoleValidator(project_boundary=(360000, 350000, 9700000, 9710000))

    def test_invalid_boundary_length_raises(self):
        with pytest.raises(ValueError, match="project_boundary must be"):
            DrillHoleValidator(project_boundary=(1, 2, 3))

    def test_issues_sorted_errors_first(self, validator, good_collars):
        dup = CollarRecord("DDH-001", 355100, 9705100, 151.0, 200.0, -60, 180, "DD")
        high_grade = [AssayInterval("DDH-001", 0.0, 1.0, 95.0, "%")]
        issues = validator.validate_all(good_collars + [dup], high_grade)
        if len(issues) > 1:
            # Errors should come before warnings
            severities = [i.severity for i in issues]
            first_warning = next((i for i, s in enumerate(severities) if s == "WARNING"), None)
            last_error = next((i for i, s in enumerate(reversed(severities)) if s == "ERROR"), None)
            if first_warning and last_error:
                assert first_warning > (len(severities) - 1 - last_error)

    def test_shallow_hole_warning(self, validator):
        shallow = [CollarRecord("DDH-SHALLOW", 355000, 9705000, 150.0, 5.0, -60, 90, "RC")]
        issues = validator.validate_collars(shallow)
        warnings = [i for i in issues if i.category == "shallow_hole"]
        assert len(warnings) == 1
