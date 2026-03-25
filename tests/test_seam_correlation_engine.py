"""Unit tests for SeamCorrelationEngine."""
import pytest
from src.seam_correlation_engine import SeamCorrelationEngine, SeamPick


def _pick(hole_id="DDH-001", top=45.0, bottom=52.0, elev=40.0, ash=4.5, cv=6200.0, **kwargs) -> SeamPick:
    return SeamPick(hole_id=hole_id, top_depth_m=top, bottom_depth_m=bottom,
                    elevation_top_masl=elev, ash_pct=ash, calorific_value_kcal=cv, **kwargs)


def _engine_with_two_picks(elev_diff=2.0) -> SeamCorrelationEngine:
    e = SeamCorrelationEngine("Tutupan")
    e.add_pick(_pick("DDH-001", elev=40.0))
    e.add_pick(_pick("DDH-002", top=47.0, bottom=54.0, elev=40.0 + elev_diff))
    return e


class TestSeamPickValidation:
    def test_valid_pick(self):
        p = _pick()
        assert p.thickness_m == pytest.approx(7.0)

    def test_bottom_le_top_raises(self):
        with pytest.raises(ValueError):
            _pick(top=50.0, bottom=45.0)

    def test_equal_depth_raises(self):
        with pytest.raises(ValueError):
            _pick(top=45.0, bottom=45.0)

    def test_thickness_computed(self):
        p = _pick(top=45.0, bottom=53.5)
        assert p.thickness_m == pytest.approx(8.5)

    def test_midpoint_depth(self):
        p = _pick(top=40.0, bottom=60.0)
        assert p.midpoint_depth_m == pytest.approx(50.0)


class TestCorrelation:
    def test_same_elevation_strong_match(self):
        e = _engine_with_two_picks(elev_diff=0.5)
        r = e.correlate_all()
        assert r["strong_pairs"] >= 1

    def test_large_elevation_diff_no_pairs(self):
        e = SeamCorrelationEngine("Test", elevation_tolerance_m=5.0)
        e.add_pick(_pick("A", elev=0.0))
        e.add_pick(_pick("B", elev=20.0))
        r = e.correlate_all()
        assert r["n_correlated_pairs"] == 0

    def test_single_pick_no_pairs(self):
        e = SeamCorrelationEngine("Test")
        e.add_pick(_pick())
        r = e.correlate_all()
        assert r["n_correlated_pairs"] == 0

    def test_same_hole_not_paired(self):
        e = SeamCorrelationEngine("Test")
        e.add_pick(_pick("A", top=40.0, bottom=47.0))
        e.add_pick(_pick("A", top=50.0, bottom=57.0))  # same hole, diff depth
        r = e.correlate_all()
        assert r["n_correlated_pairs"] == 0

    def test_confidence_level_present(self):
        e = _engine_with_two_picks(elev_diff=1.0)
        r = e.correlate_all()
        assert r["correlation_confidence"] in {"HIGH", "MODERATE", "LOW", "POOR"}

    def test_high_confidence_identical_picks(self):
        e = SeamCorrelationEngine("T", elevation_tolerance_m=20.0)
        for hid in ["A", "B", "C"]:
            e.add_pick(_pick(hid, elev=40.0, ash=4.5, cv=6200.0))
        r = e.correlate_all()
        assert r["correlation_confidence"] in {"HIGH", "MODERATE"}

    def test_uncorrelated_holes_detected(self):
        e = SeamCorrelationEngine("T", elevation_tolerance_m=2.0)
        e.add_pick(_pick("A", elev=40.0))
        e.add_pick(_pick("B", elev=40.1))
        e.add_pick(_pick("C", elev=100.0))  # very different elevation
        r = e.correlate_all()
        assert "C" in r["uncorrelated_holes"]


class TestStatistics:
    def test_thickness_statistics(self):
        e = SeamCorrelationEngine("T")
        e.add_pick(_pick(top=45.0, bottom=52.0))
        e.add_pick(_pick("B", top=45.0, bottom=53.0))
        stats = e.thickness_statistics()
        assert stats["mean_thickness_m"] == pytest.approx(7.5)
        assert stats["min_thickness_m"] == pytest.approx(7.0)
        assert stats["max_thickness_m"] == pytest.approx(8.0)

    def test_thickness_stats_empty(self):
        e = SeamCorrelationEngine("T")
        assert e.thickness_statistics() == {}

    def test_quality_statistics_computed(self):
        e = SeamCorrelationEngine("T")
        e.add_pick(_pick(ash=4.0, cv=6200.0))
        e.add_pick(_pick("B", ash=5.0, cv=6100.0))
        q = e.quality_statistics()
        assert q["ash_pct"]["mean"] == pytest.approx(4.5)
        assert q["calorific_value_kcal"]["mean"] == pytest.approx(6150.0)

    def test_dip_estimate_with_two_picks(self):
        e = _engine_with_two_picks(elev_diff=5.0)
        d = e.dip_estimate()
        assert d is not None
        assert d["elevation_range_m"] == pytest.approx(5.0)

    def test_dip_estimate_one_pick(self):
        e = SeamCorrelationEngine("T")
        e.add_pick(_pick())
        assert e.dip_estimate() is None
