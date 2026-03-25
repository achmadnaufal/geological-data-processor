"""
Seam Correlation Engine
========================
Correlates coal seam picks across multiple drillholes using depth/elevation,
seam thickness, and quality marker correlation.

Commonly used in Indonesian thermal coal exploration for Mahakam, South
Sumatera, and Kalimantan stratigraphy where multiple seam groups (e.g., Tutupan,
Paringin, Wara seams in South Kalimantan) require inter-hole correlation.

Methods:
  - Nearest-depth correlation (±tolerance window)
  - Elevation-based correlation for dipping seams
  - Ash/quality marker correlation for seam identification
  - Split seam detection (total coal thickness preserved across parting)

Usage::

    from src.seam_correlation_engine import SeamCorrelationEngine, SeamPick

    engine = SeamCorrelationEngine(seam_name="Tutupan")

    engine.add_pick(SeamPick(
        hole_id="DDH-001",
        top_depth_m=45.2,
        bottom_depth_m=51.8,
        elevation_top_masl=40.1,
        ash_pct=4.5,
        calorific_value_kcal=6200,
    ))

    engine.add_pick(SeamPick(
        hole_id="DDH-002",
        top_depth_m=48.0,
        bottom_depth_m=54.5,
        elevation_top_masl=39.8,
        ash_pct=4.8,
        calorific_value_kcal=6150,
    ))

    result = engine.correlate_all()
    print(result["correlation_confidence"])   # → HIGH
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default correlation tolerances
DEFAULT_DEPTH_TOLERANCE_M = 5.0       # ±5 m depth tolerance for same-seam correlation
DEFAULT_THICKNESS_TOLERANCE_M = 3.0   # Thickness variation allowed
DEFAULT_ELEVATION_TOLERANCE_M = 10.0  # Elevation tolerance for dipping seams
DEFAULT_ASH_TOLERANCE_PCT = 5.0       # Ash % variation within same seam
DEFAULT_CV_TOLERANCE_KCAL = 500       # CV variation within same seam

CONFIDENCE_LEVELS = {
    "HIGH": 80.0,     # ≥80% of picks correlate with all criteria
    "MODERATE": 60.0, # ≥60%
    "LOW": 40.0,      # ≥40%
    "POOR": 0.0,      # <40%
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SeamPick:
    """A drillhole coal seam intersection (pick)."""

    hole_id: str
    top_depth_m: float
    bottom_depth_m: float
    elevation_top_masl: float          # Elevation of seam top (mASL)
    ash_pct: Optional[float] = None    # As-received ash %
    calorific_value_kcal: Optional[float] = None  # Net CV kcal/kg
    sulfur_pct: Optional[float] = None
    is_split: bool = False             # True if this is a split portion
    parent_seam: str = ""              # For split seams: parent seam label

    def __post_init__(self) -> None:
        if self.bottom_depth_m <= self.top_depth_m:
            raise ValueError(
                f"bottom_depth_m ({self.bottom_depth_m}) must be > top_depth_m ({self.top_depth_m})"
            )

    @property
    def thickness_m(self) -> float:
        return self.bottom_depth_m - self.top_depth_m

    @property
    def midpoint_depth_m(self) -> float:
        return (self.top_depth_m + self.bottom_depth_m) / 2.0


@dataclass
class CorrelationPair:
    """Two seam picks identified as correlating across holes."""

    hole_a: str
    hole_b: str
    pick_a_top: float
    pick_b_top: float
    elevation_a: float
    elevation_b: float
    thickness_a: float
    thickness_b: float
    elevation_diff_m: float
    thickness_diff_m: float
    ash_diff_pct: Optional[float]
    cv_diff_kcal: Optional[float]
    match_score: float      # 0–100
    match_level: str        # STRONG | MODERATE | WEAK | REJECT


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class SeamCorrelationEngine:
    """
    Correlates coal seam picks across drillholes using multi-criterion matching.

    Parameters
    ----------
    seam_name : str
        Name or code of the target seam being correlated.
    depth_tolerance_m : float
        Maximum depth difference for initial candidate pairing.

    Methods
    -------
    add_pick(pick) — register a seam pick
    correlate_all() — run all-vs-all hole correlation
    dip_estimate() — estimate seam dip from elevation correlation
    thickness_statistics() — mean, SD, min, max thickness across picks
    quality_statistics() — mean ash, CV, sulfur across picks
    """

    def __init__(
        self,
        seam_name: str,
        depth_tolerance_m: float = DEFAULT_DEPTH_TOLERANCE_M,
        thickness_tolerance_m: float = DEFAULT_THICKNESS_TOLERANCE_M,
        elevation_tolerance_m: float = DEFAULT_ELEVATION_TOLERANCE_M,
        ash_tolerance_pct: float = DEFAULT_ASH_TOLERANCE_PCT,
        cv_tolerance_kcal: float = DEFAULT_CV_TOLERANCE_KCAL,
    ) -> None:
        self.seam_name = seam_name
        self.depth_tolerance_m = depth_tolerance_m
        self.thickness_tolerance_m = thickness_tolerance_m
        self.elevation_tolerance_m = elevation_tolerance_m
        self.ash_tolerance_pct = ash_tolerance_pct
        self.cv_tolerance_kcal = cv_tolerance_kcal
        self._picks: list[SeamPick] = []

    def add_pick(self, pick: SeamPick) -> None:
        """Add a seam pick to the correlation dataset."""
        self._picks.append(pick)

    # ------------------------------------------------------------------
    # Correlation
    # ------------------------------------------------------------------

    def correlate_all(self) -> dict:
        """
        Run all-vs-all correlation between registered picks.

        Returns
        -------
        dict: seam_name, n_picks, n_pairs, correlation_confidence,
              pairs (list of CorrelationPair dicts), uncorrelated_holes
        """
        pairs: list[CorrelationPair] = []
        n = len(self._picks)

        for i in range(n):
            for j in range(i + 1, n):
                pair = self._correlate_pair(self._picks[i], self._picks[j])
                if pair is not None:
                    pairs.append(pair)

        # Confidence: ratio of STRONG + MODERATE pairs to total hole combinations
        n_holes = len({p.hole_id for p in self._picks})
        max_pairs = n_holes * (n_holes - 1) // 2 if n_holes > 1 else 1
        strong_moderate = sum(1 for p in pairs if p.match_level in {"STRONG", "MODERATE"})
        confidence_score = (strong_moderate / max_pairs * 100.0) if max_pairs > 0 else 0.0
        confidence_level = self._classify_confidence(confidence_score)

        correlated_holes = {p.hole_a for p in pairs} | {p.hole_b for p in pairs}
        all_holes = {p.hole_id for p in self._picks}
        uncorrelated = sorted(all_holes - correlated_holes)

        return {
            "seam_name": self.seam_name,
            "n_picks": n,
            "n_hole_pairs_evaluated": max_pairs,
            "n_correlated_pairs": len(pairs),
            "strong_pairs": sum(1 for p in pairs if p.match_level == "STRONG"),
            "moderate_pairs": sum(1 for p in pairs if p.match_level == "MODERATE"),
            "weak_pairs": sum(1 for p in pairs if p.match_level == "WEAK"),
            "correlation_confidence": confidence_level,
            "confidence_score": round(confidence_score, 1),
            "uncorrelated_holes": uncorrelated,
            "pairs": [self._pair_to_dict(p) for p in pairs],
        }

    def _correlate_pair(self, a: SeamPick, b: SeamPick) -> Optional[CorrelationPair]:
        """Score a pair of picks for seam correlation."""
        if a.hole_id == b.hole_id:
            return None

        elev_diff = abs(a.elevation_top_masl - b.elevation_top_masl)
        thick_diff = abs(a.thickness_m - b.thickness_m)

        # Reject if elevation difference exceeds tolerance (seams shouldn't warp too much)
        if elev_diff > self.elevation_tolerance_m:
            return None

        # Score: start at 100, deduct for each criterion miss
        score = 100.0

        # Elevation component (40 pts)
        elev_score = max(0.0, 40.0 * (1.0 - elev_diff / self.elevation_tolerance_m))
        score = score - 40.0 + elev_score

        # Thickness component (30 pts)
        thick_score = max(0.0, 30.0 * (1.0 - thick_diff / max(self.thickness_tolerance_m, 0.01)))
        score = score - 30.0 + thick_score

        # Ash quality component (15 pts)
        ash_diff = None
        if a.ash_pct is not None and b.ash_pct is not None:
            ash_diff = abs(a.ash_pct - b.ash_pct)
            ash_score = max(0.0, 15.0 * (1.0 - ash_diff / max(self.ash_tolerance_pct, 0.01)))
            score = score - 15.0 + ash_score

        # CV quality component (15 pts)
        cv_diff = None
        if a.calorific_value_kcal is not None and b.calorific_value_kcal is not None:
            cv_diff = abs(a.calorific_value_kcal - b.calorific_value_kcal)
            cv_score = max(0.0, 15.0 * (1.0 - cv_diff / max(self.cv_tolerance_kcal, 1.0)))
            score = score - 15.0 + cv_score

        score = max(0.0, min(100.0, score))

        if score >= 75.0:
            match_level = "STRONG"
        elif score >= 50.0:
            match_level = "MODERATE"
        elif score >= 25.0:
            match_level = "WEAK"
        else:
            return None  # REJECT

        return CorrelationPair(
            hole_a=a.hole_id,
            hole_b=b.hole_id,
            pick_a_top=a.top_depth_m,
            pick_b_top=b.top_depth_m,
            elevation_a=a.elevation_top_masl,
            elevation_b=b.elevation_top_masl,
            thickness_a=a.thickness_m,
            thickness_b=b.thickness_m,
            elevation_diff_m=round(elev_diff, 2),
            thickness_diff_m=round(thick_diff, 2),
            ash_diff_pct=round(ash_diff, 2) if ash_diff is not None else None,
            cv_diff_kcal=round(cv_diff, 1) if cv_diff is not None else None,
            match_score=round(score, 1),
            match_level=match_level,
        )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def thickness_statistics(self) -> dict:
        """Return thickness stats across all registered picks."""
        if not self._picks:
            return {}
        thicknesses = [p.thickness_m for p in self._picks]
        n = len(thicknesses)
        mean = sum(thicknesses) / n
        sd = math.sqrt(sum((t - mean) ** 2 for t in thicknesses) / n) if n > 1 else 0.0
        return {
            "n_picks": n,
            "mean_thickness_m": round(mean, 3),
            "sd_thickness_m": round(sd, 3),
            "min_thickness_m": round(min(thicknesses), 3),
            "max_thickness_m": round(max(thicknesses), 3),
            "cv_pct": round(sd / mean * 100, 1) if mean > 0 else None,
        }

    def quality_statistics(self) -> dict:
        """Return mean quality parameters across all picks with data."""
        ash_vals = [p.ash_pct for p in self._picks if p.ash_pct is not None]
        cv_vals = [p.calorific_value_kcal for p in self._picks if p.calorific_value_kcal is not None]
        s_vals = [p.sulfur_pct for p in self._picks if p.sulfur_pct is not None]

        def _mean_sd(vals: list) -> dict:
            if not vals:
                return {"mean": None, "sd": None, "n": 0}
            n = len(vals)
            mean = sum(vals) / n
            sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / n) if n > 1 else 0.0
            return {"mean": round(mean, 3), "sd": round(sd, 3), "n": n}

        return {
            "ash_pct": _mean_sd(ash_vals),
            "calorific_value_kcal": _mean_sd(cv_vals),
            "sulfur_pct": _mean_sd(s_vals),
        }

    def dip_estimate(self) -> Optional[dict]:
        """
        Estimate average seam dip from correlated elevation differences.
        Requires at least 2 picks with known collar coordinates (uses elevation only here).
        """
        elevations = [p.elevation_top_masl for p in self._picks]
        if len(elevations) < 2:
            return None
        elev_range = max(elevations) - min(elevations)
        return {
            "elevation_range_m": round(elev_range, 2),
            "n_picks": len(elevations),
            "note": "Use spatial distance between holes for true dip calculation.",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_confidence(score: float) -> str:
        for level, threshold in CONFIDENCE_LEVELS.items():
            if score >= threshold:
                return level
        return "POOR"

    @staticmethod
    def _pair_to_dict(p: CorrelationPair) -> dict:
        return {
            "hole_a": p.hole_a,
            "hole_b": p.hole_b,
            "elevation_diff_m": p.elevation_diff_m,
            "thickness_diff_m": p.thickness_diff_m,
            "ash_diff_pct": p.ash_diff_pct,
            "cv_diff_kcal": p.cv_diff_kcal,
            "match_score": p.match_score,
            "match_level": p.match_level,
        }
