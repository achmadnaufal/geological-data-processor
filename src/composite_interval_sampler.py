"""
Composite Interval Sampler for Borehole Assay Databases.

Compositing is the process of combining short sample intervals into longer,
more regular intervals before geostatistical estimation. Irregular intervals
bias kriging estimates and need to be regularised.

Three compositing methods are implemented:
  1. **Bench Compositing** — composites to fixed vertical bench heights
     (common in open-pit coal/metal mine resource estimation)
  2. **Fixed Length Compositing** — composites to a regular downhole length
     (e.g., 1m, 2m, or 4m composites along borehole trace)
  3. **Seam / Zone Compositing** — composites all intervals within a named
     geological zone to a single weighted-average value

All compositing preserves weighted-average grade by accumulating
(length × grade) and dividing by total length. Missing (NaN) values within
a composite are excluded from the weighted average.

References:
    - Rossi & Deutsch (2014) Mineral Resource Estimation, ch.5 Compositing
    - Snowden (2009) Practical Geostatistics Practitioner's Course
    - JORC Code 2012 — Section 1 (Sampling) requirements

Author: github.com/achmadnaufal
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


_MISSING = float("nan")


def _is_missing(v: float) -> bool:
    """Return True if value is NaN/None/negative (missing in assay context)."""
    if v is None:
        return True
    try:
        import math
        return math.isnan(v) or v < 0
    except (TypeError, ValueError):
        return True


@dataclass
class AssayInterval:
    """
    A single assay interval from a borehole database.

    Attributes:
        hole_id: Borehole identifier.
        from_m: Start depth (metres downhole).
        to_m: End depth (metres downhole).
        grade: Numeric grade (e.g., % ash, % calorific value, g/t gold).
        grade_name: Name of the grade variable (e.g., ``ASH_PCT``, ``AU_GT``).
        zone: Optional geological zone / seam name (used in seam compositing).
    """

    hole_id: str
    from_m: float
    to_m: float
    grade: float
    grade_name: str = "GRADE"
    zone: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.hole_id.strip():
            raise ValueError("hole_id cannot be empty.")
        if self.from_m < 0:
            raise ValueError("from_m cannot be negative.")
        if self.to_m <= self.from_m:
            raise ValueError(
                f"to_m ({self.to_m}) must be greater than from_m ({self.from_m})."
            )

    @property
    def length_m(self) -> float:
        """Interval length in metres."""
        return round(self.to_m - self.from_m, 4)


@dataclass
class CompositeInterval:
    """
    An output composite interval, the result of aggregating assay intervals.

    Attributes:
        hole_id: Parent borehole identifier.
        from_m: Composite start depth (m).
        to_m: Composite end depth (m).
        length_m: Composite length (m).
        weighted_grade: Length-weighted average grade.
        grade_name: Grade variable name.
        n_samples: Number of assay intervals merged into this composite.
        zone: Zone label (if applicable).
    """

    hole_id: str
    from_m: float
    to_m: float
    length_m: float
    weighted_grade: float
    grade_name: str
    n_samples: int
    zone: Optional[str] = None


class CompositeIntervalSampler:
    """
    Composites raw assay intervals to regular or zone-based intervals.

    Supports three compositing strategies:
    - **fixed_length** — regularise to a uniform downhole length
    - **bench** — regularise to open-pit bench heights
    - **seam** — aggregate per geological zone/seam

    Attributes:
        intervals (list[AssayInterval]): Registered raw assay intervals.
        grade_name (str): Default grade variable name.

    Example::

        sampler = CompositeIntervalSampler(grade_name="ASH_PCT")
        sampler.add_interval(AssayInterval("DDH-001", 0.0, 0.55, 12.5, zone="A-Seam"))
        sampler.add_interval(AssayInterval("DDH-001", 0.55, 1.10, 14.2, zone="A-Seam"))
        sampler.add_interval(AssayInterval("DDH-001", 1.10, 1.90, 11.8, zone="A-Seam"))

        # Seam composite
        composites = sampler.seam_composite("DDH-001")
        for c in composites:
            print(f"{c.zone}: {c.weighted_grade:.2f}% ash over {c.length_m:.2f}m")

        # Fixed 1m composite
        composites = sampler.fixed_length_composite("DDH-001", composite_length=1.0)
        for c in composites:
            print(f"{c.from_m:.2f}–{c.to_m:.2f}m: {c.weighted_grade:.2f}% ash")
    """

    def __init__(self, grade_name: str = "GRADE") -> None:
        """
        Initialize the sampler.

        Args:
            grade_name: Default name for the grade variable (informational).
        """
        self.grade_name = grade_name
        self.intervals: List[AssayInterval] = []

    # ------------------------------------------------------------------
    # Data management
    # ------------------------------------------------------------------

    def add_interval(self, interval: AssayInterval) -> None:
        """
        Register a raw assay interval.

        Args:
            interval: An :class:`AssayInterval` instance.
        """
        self.intervals.append(interval)

    def add_intervals_bulk(self, intervals: List[AssayInterval]) -> int:
        """
        Bulk-add intervals.

        Args:
            intervals: List of :class:`AssayInterval` instances.

        Returns:
            Number of intervals added.
        """
        for iv in intervals:
            self.intervals.append(iv)
        return len(intervals)

    def get_hole_intervals(self, hole_id: str) -> List[AssayInterval]:
        """
        Return intervals for a specific borehole, sorted by from_m.

        Args:
            hole_id: Borehole identifier.

        Returns:
            Sorted list of :class:`AssayInterval` objects.

        Raises:
            KeyError: If hole_id is not found.
        """
        intervals = [iv for iv in self.intervals if iv.hole_id == hole_id]
        if not intervals:
            raise KeyError(f"No intervals found for hole_id '{hole_id}'.")
        return sorted(intervals, key=lambda iv: iv.from_m)

    def hole_ids(self) -> List[str]:
        """Return sorted list of unique hole IDs."""
        return sorted({iv.hole_id for iv in self.intervals})

    # ------------------------------------------------------------------
    # Fixed-length compositing
    # ------------------------------------------------------------------

    def fixed_length_composite(
        self,
        hole_id: str,
        composite_length: float = 1.0,
        min_coverage: float = 0.5,
    ) -> List[CompositeInterval]:
        """
        Composite assay intervals to a fixed downhole composite length.

        Intervals are split proportionally to align with composite boundaries.
        A composite must have at least ``min_coverage`` fraction of the target
        length covered by valid (non-missing) data to be included.

        Args:
            hole_id: Borehole to composite.
            composite_length: Target composite length in metres (default 1.0m).
            min_coverage: Minimum fraction of composite length that must have
                data (0–1). Composites below this threshold are discarded.

        Returns:
            List of :class:`CompositeInterval` objects sorted by depth.

        Raises:
            KeyError: If hole_id is not found.
            ValueError: If composite_length <= 0 or min_coverage not in (0,1].
        """
        if composite_length <= 0:
            raise ValueError("composite_length must be positive.")
        if not (0 < min_coverage <= 1):
            raise ValueError("min_coverage must be in (0, 1].")

        raw = self.get_hole_intervals(hole_id)
        if not raw:
            return []

        # Determine the extent of data
        start = raw[0].from_m
        end = raw[-1].to_m

        composites: List[CompositeInterval] = []
        comp_start = start

        while comp_start < end:
            comp_end = comp_start + composite_length
            if comp_end > end:
                comp_end = end  # Tail composite (may be shorter)

            grade_length_sum = 0.0
            valid_length = 0.0
            n_samples = 0

            for iv in raw:
                # Overlap between composite window and assay interval
                overlap_start = max(iv.from_m, comp_start)
                overlap_end = min(iv.to_m, comp_end)
                if overlap_end <= overlap_start:
                    continue

                overlap = overlap_end - overlap_start

                if not _is_missing(iv.grade):
                    grade_length_sum += iv.grade * overlap
                    valid_length += overlap
                    n_samples += 1

            if valid_length >= composite_length * min_coverage:
                weighted_grade = round(grade_length_sum / valid_length, 4)
                composites.append(
                    CompositeInterval(
                        hole_id=hole_id,
                        from_m=round(comp_start, 3),
                        to_m=round(comp_end, 3),
                        length_m=round(comp_end - comp_start, 3),
                        weighted_grade=weighted_grade,
                        grade_name=self.grade_name,
                        n_samples=n_samples,
                    )
                )

            comp_start = comp_end

        return composites

    # ------------------------------------------------------------------
    # Bench compositing
    # ------------------------------------------------------------------

    def bench_composite(
        self,
        hole_id: str,
        bench_height_m: float = 5.0,
        bench_origin_rl: float = 0.0,
    ) -> List[CompositeInterval]:
        """
        Composite intervals to fixed bench heights (open-pit mining convention).

        Bench compositing aligns to mine bench levels rather than from the
        collar. This is common in coal and laterite resource estimation.

        Args:
            hole_id: Borehole to composite.
            bench_height_m: Bench height in metres (default 5m).
            bench_origin_rl: Elevation offset for bench alignment (RL in metres).

        Returns:
            List of :class:`CompositeInterval` objects.

        Raises:
            KeyError: If hole_id not found.
            ValueError: If bench_height_m <= 0.
        """
        if bench_height_m <= 0:
            raise ValueError("bench_height_m must be positive.")
        # Bench compositing is equivalent to fixed-length compositing
        # aligned to the bench height (simplified: treat depth as RL offset)
        return self.fixed_length_composite(
            hole_id=hole_id,
            composite_length=bench_height_m,
            min_coverage=0.3,  # Typically more lenient for bench compositing
        )

    # ------------------------------------------------------------------
    # Seam / zone compositing
    # ------------------------------------------------------------------

    def seam_composite(self, hole_id: str) -> List[CompositeInterval]:
        """
        Composite all intervals within the same geological zone to a single value.

        If intervals have no zone assigned, they are grouped under ``"UNDEFINED"``.

        Args:
            hole_id: Borehole to composite.

        Returns:
            List of :class:`CompositeInterval` objects, one per zone, sorted by
            the shallowest depth of each zone.

        Raises:
            KeyError: If hole_id not found.
        """
        raw = self.get_hole_intervals(hole_id)

        zone_data: Dict[str, Dict] = {}
        for iv in raw:
            zone = iv.zone or "UNDEFINED"
            if zone not in zone_data:
                zone_data[zone] = {
                    "grade_length": 0.0,
                    "valid_length": 0.0,
                    "from_m": iv.from_m,
                    "to_m": iv.to_m,
                    "n_samples": 0,
                }
            else:
                zone_data[zone]["from_m"] = min(zone_data[zone]["from_m"], iv.from_m)
                zone_data[zone]["to_m"] = max(zone_data[zone]["to_m"], iv.to_m)

            if not _is_missing(iv.grade):
                zone_data[zone]["grade_length"] += iv.grade * iv.length_m
                zone_data[zone]["valid_length"] += iv.length_m
                zone_data[zone]["n_samples"] += 1

        composites = []
        for zone, data in zone_data.items():
            if data["valid_length"] == 0:
                continue
            weighted_grade = round(data["grade_length"] / data["valid_length"], 4)
            length = round(data["to_m"] - data["from_m"], 3)
            composites.append(
                CompositeInterval(
                    hole_id=hole_id,
                    from_m=round(data["from_m"], 3),
                    to_m=round(data["to_m"], 3),
                    length_m=length,
                    weighted_grade=weighted_grade,
                    grade_name=self.grade_name,
                    n_samples=data["n_samples"],
                    zone=zone,
                )
            )

        return sorted(composites, key=lambda c: c.from_m)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def hole_summary(self, hole_id: str) -> Dict:
        """
        Return a summary of raw assay data for a borehole.

        Args:
            hole_id: Borehole identifier.

        Returns:
            dict with: ``hole_id``, ``n_intervals``, ``total_length_m``,
            ``min_grade``, ``max_grade``, ``weighted_avg_grade``, ``zones``.
        """
        raw = self.get_hole_intervals(hole_id)
        valid = [iv for iv in raw if not _is_missing(iv.grade)]
        total_length = sum(iv.length_m for iv in raw)
        valid_length = sum(iv.length_m for iv in valid)
        grade_length = sum(iv.grade * iv.length_m for iv in valid)
        zones = sorted({iv.zone for iv in raw if iv.zone is not None})

        return {
            "hole_id": hole_id,
            "n_intervals": len(raw),
            "total_length_m": round(total_length, 2),
            "valid_length_m": round(valid_length, 2),
            "min_grade": round(min(iv.grade for iv in valid), 3) if valid else None,
            "max_grade": round(max(iv.grade for iv in valid), 3) if valid else None,
            "weighted_avg_grade": round(grade_length / valid_length, 4) if valid_length > 0 else None,
            "zones": zones,
        }

    def __len__(self) -> int:
        return len(self.intervals)

    def __repr__(self) -> str:
        return (
            f"CompositeIntervalSampler(grade={self.grade_name!r}, "
            f"intervals={len(self.intervals)}, holes={len(self.hole_ids())})"
        )
