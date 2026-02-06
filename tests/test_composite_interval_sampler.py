"""Unit tests for CompositeIntervalSampler."""
import pytest
from src.composite_interval_sampler import (
    CompositeIntervalSampler, AssayInterval, CompositeInterval
)


@pytest.fixture
def sampler():
    s = CompositeIntervalSampler(grade_name="ASH_PCT")
    # DDH-001 — 3 seams (A, B, C)
    intervals = [
        AssayInterval("DDH-001", 0.00, 0.55, 12.5, zone="A-Seam"),
        AssayInterval("DDH-001", 0.55, 1.10, 14.2, zone="A-Seam"),
        AssayInterval("DDH-001", 1.10, 1.90, 11.8, zone="A-Seam"),
        AssayInterval("DDH-001", 1.90, 3.20, 28.5, zone="Interburden"),
        AssayInterval("DDH-001", 3.20, 3.80, 10.2, zone="B-Seam"),
        AssayInterval("DDH-001", 3.80, 4.40, 9.8, zone="B-Seam"),
        AssayInterval("DDH-001", 4.40, 5.90, 9.1, zone="B-Seam"),
        AssayInterval("DDH-001", 5.90, 7.50, 35.0, zone="Interburden"),
        AssayInterval("DDH-001", 7.50, 8.20, 8.5, zone="C-Seam"),
        AssayInterval("DDH-001", 8.20, 9.00, 7.9, zone="C-Seam"),
    ]
    s.add_intervals_bulk(intervals)
    # DDH-002 — simpler profile
    s.add_interval(AssayInterval("DDH-002", 0.00, 1.00, 15.0, zone="Main-Seam"))
    s.add_interval(AssayInterval("DDH-002", 1.00, 2.00, 13.5, zone="Main-Seam"))
    s.add_interval(AssayInterval("DDH-002", 2.00, 3.00, 16.2, zone="Main-Seam"))
    return s


# --- AssayInterval validation ---

def test_empty_hole_id():
    with pytest.raises(ValueError, match="hole_id"):
        AssayInterval("", 0.0, 1.0, 10.0)

def test_negative_from_m():
    with pytest.raises(ValueError, match="from_m"):
        AssayInterval("H1", -1.0, 1.0, 10.0)

def test_to_m_less_than_from_m():
    with pytest.raises(ValueError, match="to_m"):
        AssayInterval("H1", 5.0, 3.0, 10.0)

def test_to_m_equal_from_m():
    with pytest.raises(ValueError, match="to_m"):
        AssayInterval("H1", 2.0, 2.0, 10.0)

def test_length_m_property():
    iv = AssayInterval("H1", 1.5, 3.0, 10.0)
    assert abs(iv.length_m - 1.5) < 0.001


# --- Sampler counts ---

def test_len(sampler):
    assert len(sampler) == 13

def test_hole_ids(sampler):
    ids = sampler.hole_ids()
    assert "DDH-001" in ids
    assert "DDH-002" in ids

def test_bulk_add():
    s = CompositeIntervalSampler()
    n = s.add_intervals_bulk([
        AssayInterval("H1", 0.0, 1.0, 5.0),
        AssayInterval("H1", 1.0, 2.0, 6.0),
    ])
    assert n == 2


# --- get_hole_intervals ---

def test_get_hole_intervals_sorted(sampler):
    intervals = sampler.get_hole_intervals("DDH-001")
    depths = [iv.from_m for iv in intervals]
    assert depths == sorted(depths)

def test_get_hole_intervals_missing_raises(sampler):
    with pytest.raises(KeyError, match="DDH-999"):
        sampler.get_hole_intervals("DDH-999")


# --- Fixed-length compositing ---

def test_fixed_length_returns_composites(sampler):
    composites = sampler.fixed_length_composite("DDH-001", composite_length=1.0)
    assert len(composites) > 0

def test_fixed_length_no_overlap(sampler):
    comps = sampler.fixed_length_composite("DDH-001", composite_length=1.0)
    for i in range(len(comps) - 1):
        assert comps[i].to_m <= comps[i+1].from_m + 0.001

def test_fixed_length_grade_weighted(sampler):
    # DDH-002: uniform 1m intervals, 1m composite → single composite per interval
    comps = sampler.fixed_length_composite("DDH-002", composite_length=1.0)
    # 3 intervals of exactly 1m → 3 composites
    assert len(comps) == 3
    assert abs(comps[0].weighted_grade - 15.0) < 0.01

def test_fixed_length_composite_spans_two_intervals(sampler):
    # DDH-002 with 2m composite: two 1m intervals → one 2m composite
    comps = sampler.fixed_length_composite("DDH-002", composite_length=2.0)
    # 3m total with 2m composites → 2 composites (2m + 1m)
    assert len(comps) >= 1

def test_fixed_length_invalid_length(sampler):
    with pytest.raises(ValueError, match="composite_length"):
        sampler.fixed_length_composite("DDH-001", composite_length=0)

def test_fixed_length_invalid_coverage(sampler):
    with pytest.raises(ValueError, match="min_coverage"):
        sampler.fixed_length_composite("DDH-001", min_coverage=0.0)

def test_composite_result_fields(sampler):
    comps = sampler.fixed_length_composite("DDH-002", composite_length=1.0)
    c = comps[0]
    assert hasattr(c, "hole_id")
    assert hasattr(c, "weighted_grade")
    assert hasattr(c, "n_samples")
    assert hasattr(c, "length_m")


# --- Seam compositing ---

def test_seam_composite_returns_per_zone(sampler):
    comps = sampler.seam_composite("DDH-001")
    zones = {c.zone for c in comps}
    assert "A-Seam" in zones
    assert "B-Seam" in zones
    assert "C-Seam" in zones

def test_seam_composite_weighted_grade_a_seam(sampler):
    comps = sampler.seam_composite("DDH-001")
    a_seam = next(c for c in comps if c.zone == "A-Seam")
    # A-Seam: (0.55*12.5 + 0.55*14.2 + 0.80*11.8) / (0.55+0.55+0.80)
    expected_length = 0.55 + 0.55 + 0.80
    expected_grade = (0.55*12.5 + 0.55*14.2 + 0.80*11.8) / expected_length
    assert abs(a_seam.weighted_grade - expected_grade) < 0.01

def test_seam_composite_sorted_by_depth(sampler):
    comps = sampler.seam_composite("DDH-001")
    depths = [c.from_m for c in comps]
    assert depths == sorted(depths)

def test_seam_composite_no_zone(sampler):
    # Add interval without zone
    s = CompositeIntervalSampler()
    s.add_interval(AssayInterval("H1", 0.0, 2.0, 10.0))  # no zone
    comps = s.seam_composite("H1")
    assert comps[0].zone == "UNDEFINED"


# --- Bench compositing ---

def test_bench_composite_returns_composites(sampler):
    comps = sampler.bench_composite("DDH-001", bench_height_m=2.0)
    assert len(comps) > 0

def test_bench_composite_invalid_height(sampler):
    with pytest.raises(ValueError, match="bench_height_m"):
        sampler.bench_composite("DDH-001", bench_height_m=0)


# --- Hole summary ---

def test_hole_summary_keys(sampler):
    summary = sampler.hole_summary("DDH-001")
    for key in ["hole_id", "n_intervals", "total_length_m",
                "min_grade", "max_grade", "weighted_avg_grade", "zones"]:
        assert key in summary

def test_hole_summary_zones(sampler):
    summary = sampler.hole_summary("DDH-001")
    assert "A-Seam" in summary["zones"]

def test_hole_summary_total_length(sampler):
    summary = sampler.hole_summary("DDH-001")
    assert abs(summary["total_length_m"] - 9.0) < 0.01


# --- Repr ---

def test_repr(sampler):
    assert "CompositeIntervalSampler" in repr(sampler)
    assert "ASH_PCT" in repr(sampler)
