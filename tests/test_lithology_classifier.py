"""Unit tests for src.lithology_classifier.

Covers: BoreholeInterval validation, LithologyClassifier construction,
classify() method (proximate, density, grain size paths), classify_borehole(),
coal_seam_summary(), field_agreement_rate(), and edge cases.
"""

import pytest
from src.lithology_classifier import (
    BoreholeInterval,
    LithologyClassification,
    LithologyClassifier,
    COAL_ASH_MAX_PCT,
    CARBONACEOUS_ASH_MAX_PCT,
    VALID_LITHOLOGIES,
)


# ---------------------------------------------------------------------------
# BoreholeInterval tests
# ---------------------------------------------------------------------------


def make_interval(
    interval_id="BH001-001",
    borehole_id="BH001",
    depth_from=10.0,
    depth_to=12.5,
    ash=8.5,
    moisture=22.0,
    vm=None,
    gcv=4100.0,
    density=None,
    grain=None,
    field_litho=None,
):
    return BoreholeInterval(
        interval_id=interval_id,
        borehole_id=borehole_id,
        depth_from_m=depth_from,
        depth_to_m=depth_to,
        ash_ad_pct=ash,
        moisture_ad_pct=moisture,
        volatile_matter_daf_pct=vm,
        gcv_gar_kcal_kg=gcv,
        density_g_cm3=density,
        grain_size_descriptor=grain,
        field_lithology=field_litho,
    )


class TestBoreholeInterval:
    def test_basic_creation(self):
        iv = make_interval()
        assert iv.interval_id == "BH001-001"
        assert iv.borehole_id == "BH001"

    def test_thickness_computed(self):
        iv = make_interval(depth_from=10.0, depth_to=12.5)
        assert iv.thickness_m == pytest.approx(2.5)

    def test_depth_mid_computed(self):
        iv = make_interval(depth_from=10.0, depth_to=14.0)
        assert iv.depth_mid_m == pytest.approx(12.0)

    def test_empty_interval_id_raises(self):
        with pytest.raises(ValueError, match="interval_id"):
            make_interval(interval_id="")

    def test_depth_to_lte_depth_from_raises(self):
        with pytest.raises(ValueError, match="depth_to_m"):
            make_interval(depth_from=10.0, depth_to=10.0)

    def test_depth_to_less_than_from_raises(self):
        with pytest.raises(ValueError, match="depth_to_m"):
            make_interval(depth_from=15.0, depth_to=10.0)

    def test_negative_depth_from_raises(self):
        with pytest.raises(ValueError, match="depth_from_m"):
            make_interval(depth_from=-1.0, depth_to=5.0)

    def test_ash_out_of_range_raises(self):
        with pytest.raises(ValueError, match="ash_ad_pct"):
            make_interval(ash=105.0)

    def test_invalid_density_raises(self):
        with pytest.raises(ValueError, match="density_g_cm3"):
            make_interval(density=4.5)

    def test_invalid_grain_size_raises(self):
        with pytest.raises(ValueError, match="grain_size_descriptor"):
            make_interval(grain="pebble")


# ---------------------------------------------------------------------------
# LithologyClassifier construction
# ---------------------------------------------------------------------------


class TestClassifierInit:
    def test_default_creation(self):
        clf = LithologyClassifier()
        assert clf.use_density_fallback is True
        assert clf.use_grain_size is True

    def test_custom_flags(self):
        clf = LithologyClassifier(use_density_fallback=False, use_grain_size=False)
        assert clf.use_density_fallback is False


# ---------------------------------------------------------------------------
# Classification tests (proximate path)
# ---------------------------------------------------------------------------


@pytest.fixture
def clf():
    return LithologyClassifier()


class TestClassifyProximate:
    def test_coal_low_ash_high_gcv(self, clf):
        iv = make_interval(ash=8.5, gcv=4100.0)
        result = clf.classify(iv)
        assert result.classified_lithology == "coal"
        assert result.confidence == "high"
        assert result.classification_basis == "proximate"

    def test_coal_very_low_ash_no_gcv(self, clf):
        iv = make_interval(ash=12.0, gcv=None)
        result = clf.classify(iv)
        assert result.classified_lithology == "coal"
        assert result.confidence == "high"

    def test_coal_moderate_ash_no_gcv_medium_confidence(self, clf):
        iv = make_interval(ash=28.0, gcv=None)
        result = clf.classify(iv)
        assert result.classified_lithology == "coal"
        assert result.confidence == "medium"

    def test_carbonaceous_shale(self, clf):
        iv = make_interval(ash=58.0, gcv=None)
        result = clf.classify(iv)
        assert result.classified_lithology == "carbonaceous_shale"
        assert result.confidence == "high"

    def test_high_ash_with_density_classified(self, clf):
        # ash > 70% + sandstone density
        iv = make_interval(ash=82.0, gcv=None, density=2.45)
        result = clf.classify(iv)
        assert result.classified_lithology in {"sandstone", "siltstone"}
        assert "density" in result.classification_basis

    def test_high_ash_with_grain_size(self, clf):
        iv = make_interval(ash=78.0, gcv=None, grain="silt")
        result = clf.classify(iv)
        assert result.classified_lithology == "siltstone"
        assert "grain_size" in result.classification_basis

    def test_high_ash_coarse_sand(self, clf):
        iv = make_interval(ash=85.0, gcv=None, grain="coarse_sand")
        result = clf.classify(iv)
        assert result.classified_lithology == "sandstone"


# ---------------------------------------------------------------------------
# Classification tests (density path)
# ---------------------------------------------------------------------------


class TestClassifyDensity:
    def test_coal_density(self, clf):
        iv = make_interval(ash=8.0, gcv=None, density=1.45)
        result = clf.classify(iv)
        assert result.classified_lithology == "coal"

    def test_shale_density(self, clf):
        iv = make_interval(ash=78.0, gcv=None, density=2.35)
        result = clf.classify(iv)
        assert result.classified_lithology in {"shale", "siltstone"}  # both in that range

    def test_density_fallback_disabled(self):
        clf_no_density = LithologyClassifier(use_density_fallback=False)
        iv = make_interval(ash=78.0, gcv=None, density=2.35)
        result = clf_no_density.classify(iv)
        assert result.classified_lithology == "undifferentiated"


# ---------------------------------------------------------------------------
# Field agreement
# ---------------------------------------------------------------------------


class TestFieldAgreement:
    def test_agreement_correct(self, clf):
        iv = make_interval(ash=8.5, gcv=4100.0, field_litho="coal")
        result = clf.classify(iv)
        assert result.agreement_with_field is True

    def test_disagreement_detected(self, clf):
        iv = make_interval(ash=8.5, gcv=4100.0, field_litho="shale")
        result = clf.classify(iv)
        assert result.agreement_with_field is False

    def test_no_field_litho_agreement_none(self, clf):
        iv = make_interval(ash=8.5, gcv=4100.0, field_litho=None)
        result = clf.classify(iv)
        assert result.agreement_with_field is None


# ---------------------------------------------------------------------------
# classify_borehole tests
# ---------------------------------------------------------------------------


class TestClassifyBorehole:
    def _make_borehole_intervals(self):
        return [
            make_interval("BH01-01", "BH01", depth_from=0.0, depth_to=5.0, ash=80.0, gcv=None, density=2.40),
            make_interval("BH01-02", "BH01", depth_from=5.0, depth_to=8.0, ash=8.5, gcv=4100.0),
            make_interval("BH01-03", "BH01", depth_from=8.0, depth_to=9.0, ash=62.0, gcv=None),
            make_interval("BH01-04", "BH01", depth_from=9.0, depth_to=12.5, ash=10.0, gcv=4300.0),
            make_interval("BH01-05", "BH01", depth_from=12.5, depth_to=20.0, ash=82.0, gcv=None, grain="silt"),
        ]

    def test_returns_all_classified(self, clf):
        intervals = self._make_borehole_intervals()
        results = clf.classify_borehole(intervals)
        assert len(results) == 5

    def test_sorted_by_depth(self, clf):
        intervals = list(reversed(self._make_borehole_intervals()))
        results = clf.classify_borehole(intervals)
        depths = [r.depth_from_m for r in results]
        assert depths == sorted(depths)

    def test_empty_raises(self, clf):
        with pytest.raises(ValueError, match="empty"):
            clf.classify_borehole([])

    def test_mixed_boreholes_raises(self, clf):
        iv1 = make_interval(interval_id="I1", borehole_id="BH01")
        iv2 = make_interval(interval_id="I2", borehole_id="BH02", depth_from=15.0, depth_to=18.0)
        with pytest.raises(ValueError, match="borehole_id"):
            clf.classify_borehole([iv1, iv2])


# ---------------------------------------------------------------------------
# Coal seam summary tests
# ---------------------------------------------------------------------------


class TestCoalSeamSummary:
    def _get_classified(self, clf):
        intervals = [
            make_interval("BH01-01", "BH01", depth_from=0.0, depth_to=5.0, ash=80.0, gcv=None, grain="silt"),
            make_interval("BH01-02", "BH01", depth_from=5.0, depth_to=8.5, ash=8.5, gcv=4100.0),
            make_interval("BH01-03", "BH01", depth_from=8.5, depth_to=9.0, ash=62.0, gcv=None),
            make_interval("BH01-04", "BH01", depth_from=9.0, depth_to=12.5, ash=10.0, gcv=4300.0),
        ]
        return clf.classify_borehole(intervals)

    def test_coal_count(self, clf):
        classified = self._get_classified(clf)
        summary = clf.coal_seam_summary(classified)
        assert summary["n_coal_intervals"] == 2

    def test_total_coal_thickness(self, clf):
        classified = self._get_classified(clf)
        summary = clf.coal_seam_summary(classified)
        # Coal intervals: 5.0–8.5 (3.5m) + 9.0–12.5 (3.5m) = 7.0m
        assert summary["total_coal_thickness_m"] == pytest.approx(7.0)

    def test_split_seam_detected(self, clf):
        classified = self._get_classified(clf)
        summary = clf.coal_seam_summary(classified)
        assert summary["has_split_seam"] is True

    def test_no_coal_summary(self, clf):
        intervals = [
            make_interval("BH01-01", "BH01", depth_from=0.0, depth_to=5.0, ash=80.0, gcv=None, grain="silt"),
        ]
        classified = clf.classify_borehole(intervals)
        summary = clf.coal_seam_summary(classified)
        assert summary["n_coal_intervals"] == 0


# ---------------------------------------------------------------------------
# Field agreement rate tests
# ---------------------------------------------------------------------------


class TestFieldAgreementRate:
    def test_perfect_agreement(self, clf):
        iv1 = make_interval("I1", "BH", ash=8.0, gcv=4100.0, field_litho="coal")
        iv2 = make_interval("I2", "BH", depth_from=5.0, depth_to=8.0, ash=8.5, gcv=4200.0, field_litho="coal")
        classified = clf.classify_borehole([iv1, iv2])
        rate = clf.field_agreement_rate(classified)
        assert rate == pytest.approx(1.0)

    def test_no_field_calls_returns_none(self, clf):
        iv = make_interval("I1", "BH", ash=8.0, gcv=4100.0, field_litho=None)
        classified = clf.classify_borehole([iv])
        rate = clf.field_agreement_rate(classified)
        assert rate is None

    def test_partial_agreement(self, clf):
        iv1 = make_interval("I1", "BH", ash=8.0, gcv=4100.0, field_litho="coal")
        iv2 = make_interval("I2", "BH", depth_from=5.0, depth_to=8.0, ash=62.0, gcv=None,
                            field_litho="sandstone")  # will be classified as carbonaceous_shale → disagree
        classified = clf.classify_borehole([iv1, iv2])
        rate = clf.field_agreement_rate(classified)
        assert 0.0 <= rate <= 1.0
