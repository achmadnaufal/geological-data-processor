"""
Block Model Grade Estimator using Inverse Distance Weighting (IDW).

Generates a 3D block model by interpolating grade values (e.g., coal quality
parameters: ash, sulfur, GCV) from drill hole composite data using the
Inverse Distance Weighting method.

IDW is widely used in mineral resource estimation as a transparent, JORC/NI 43-101
compliant method for producing resource block models, particularly for coal
deposits where grade continuity is typically high and variogram modelling
may be less critical than in hard-rock deposits.

Methodology references:
- JORC Code 2012 — Australasian Code for Reporting of Exploration Results,
  Mineral Resources and Ore Reserves
- Isaaks & Srivastava (1989) Applied Geostatistics, Oxford University Press
- Sinclair & Blackwell (2002) Applied Mineral Inventory Estimation,
  Cambridge University Press
- Deutsch & Journel (1997) GSLIB: Geostatistical Software Library, 2nd Ed.

Author: github.com/achmadnaufal
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class DrillHoleComposite:
    """A single composite interval from a drill hole used as an estimation sample.

    Attributes:
        hole_id: Drill hole identifier.
        easting: Easting coordinate (metres, UTM or local grid).
        northing: Northing coordinate (metres).
        mid_depth: Mid-depth of the composite interval (metres from collar).
        grade_values: Dict mapping parameter name to measured grade value.
            E.g. ``{"ash_pct": 8.5, "total_sulfur_pct": 0.38, "gcv_kcal_kg": 6500}``.
        composite_length_m: Length of the composite interval (metres). Default 1.0.
    """

    hole_id: str
    easting: float
    northing: float
    mid_depth: float
    grade_values: Dict[str, float]
    composite_length_m: float = 1.0


@dataclass
class BlockNode:
    """A single block in the 3D block model grid.

    Attributes:
        block_id: Unique block identifier (e.g., 'E500_N100_D50').
        easting: Block centroid easting (metres).
        northing: Block centroid northing (metres).
        depth: Block centroid depth (metres).
        estimated_grades: Interpolated grade values per parameter.
        sample_count: Number of composites used in the estimate.
        mean_distance_m: Mean distance to contributing samples (metres).
    """

    block_id: str
    easting: float
    northing: float
    depth: float
    estimated_grades: Dict[str, float] = field(default_factory=dict)
    sample_count: int = 0
    mean_distance_m: float = 0.0


class BlockModelEstimator:
    """Generates a coal deposit block model using Inverse Distance Weighting (IDW).

    Interpolates quality parameters (ash, sulfur, GCV, moisture, etc.) from
    drill hole composite data onto a regular 3D block grid. Supports
    anisotropic search ellipsoids and configurable IDW power parameters.

    The IDW formula for each block:

    .. code-block::

        Z(x) = Σ [w_i * z_i] / Σ w_i
        where w_i = 1 / d_i^p

        d_i = Euclidean distance from block centroid to sample i
        p   = IDW power (higher = more localised; typically 2)

    Args:
        power: IDW exponent (default 2.0). Higher values give more weight to
            nearby samples (more local estimation).
        max_search_radius_m: Maximum search distance. Samples beyond this radius
            are excluded. Default 500.0 m.
        min_samples: Minimum number of composites required to estimate a block.
            Blocks with fewer contributing samples will have ``estimated_grades``
            set to ``None`` values. Default 3.
        max_samples: Maximum number of nearest composites to use per block. Default 20.

    Example::

        composites = [
            DrillHoleComposite("DDH001", 500, 100, 50, {"ash_pct": 8.5, "gcv_kcal_kg": 6500}),
            DrillHoleComposite("DDH002", 550, 150, 55, {"ash_pct": 9.2, "gcv_kcal_kg": 6350}),
            DrillHoleComposite("DDH003", 520, 200, 48, {"ash_pct": 7.8, "gcv_kcal_kg": 6700}),
        ]
        estimator = BlockModelEstimator(power=2.0, max_search_radius_m=200.0)
        block = estimator.estimate_block(
            block_id="B1",
            easting=520.0, northing=150.0, depth=52.0,
            composites=composites,
        )
        print(block.estimated_grades)
    """

    def __init__(
        self,
        power: float = 2.0,
        max_search_radius_m: float = 500.0,
        min_samples: int = 3,
        max_samples: int = 20,
    ) -> None:
        if power <= 0:
            raise ValueError(f"power must be > 0, got {power}.")
        if max_search_radius_m <= 0:
            raise ValueError(f"max_search_radius_m must be > 0, got {max_search_radius_m}.")
        if min_samples < 1:
            raise ValueError(f"min_samples must be ≥ 1, got {min_samples}.")
        if max_samples < min_samples:
            raise ValueError(
                f"max_samples ({max_samples}) must be ≥ min_samples ({min_samples})."
            )

        self._power = power
        self._search_radius = max_search_radius_m
        self._min_samples = min_samples
        self._max_samples = max_samples

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_block(
        self,
        block_id: str,
        easting: float,
        northing: float,
        depth: float,
        composites: List[DrillHoleComposite],
        parameters: Optional[List[str]] = None,
    ) -> BlockNode:
        """Estimate grade values for a single block centroid.

        Args:
            block_id: Unique identifier for this block.
            easting: Block centroid easting (metres).
            northing: Block centroid northing (metres).
            depth: Block centroid depth (metres).
            composites: List of DrillHoleComposite samples.
            parameters: Optional list of grade parameter names to interpolate.
                If None, all parameters present in the composite data are used.

        Returns:
            BlockNode with interpolated grades, sample count, and mean distance.
            If fewer than ``min_samples`` are within the search radius,
            ``estimated_grades`` will contain None for all parameters and
            ``sample_count`` will be 0.
        """
        # Find samples within search radius, sorted by distance
        candidates = []
        for comp in composites:
            dist = self._distance(easting, northing, depth,
                                  comp.easting, comp.northing, comp.mid_depth)
            if dist <= self._search_radius:
                candidates.append((dist, comp))

        candidates.sort(key=lambda x: x[0])
        candidates = candidates[: self._max_samples]

        if len(candidates) < self._min_samples:
            return BlockNode(
                block_id=block_id,
                easting=easting,
                northing=northing,
                depth=depth,
                estimated_grades={},
                sample_count=len(candidates),
                mean_distance_m=0.0,
            )

        # Determine parameters to estimate
        if parameters is None:
            param_set: set = set()
            for _, comp in candidates:
                param_set.update(comp.grade_values.keys())
            parameters = sorted(param_set)

        # IDW interpolation per parameter
        estimated: Dict[str, float] = {}
        for param in parameters:
            valid_pairs = [
                (d, comp.grade_values[param])
                for d, comp in candidates
                if param in comp.grade_values
            ]
            if not valid_pairs:
                continue

            # Handle coincident samples (distance = 0) — use exact value
            exact = [v for d, v in valid_pairs if d == 0.0]
            if exact:
                estimated[param] = round(exact[0], 4)
            else:
                weights = [1.0 / (d ** self._power) for d, _ in valid_pairs]
                total_w = sum(weights)
                estimated[param] = round(
                    sum(w * v for w, (_, v) in zip(weights, valid_pairs)) / total_w,
                    4,
                )

        mean_dist = sum(d for d, _ in candidates) / len(candidates)

        return BlockNode(
            block_id=block_id,
            easting=easting,
            northing=northing,
            depth=depth,
            estimated_grades=estimated,
            sample_count=len(candidates),
            mean_distance_m=round(mean_dist, 2),
        )

    def generate_model(
        self,
        composites: List[DrillHoleComposite],
        east_range: Tuple[float, float],
        north_range: Tuple[float, float],
        depth_range: Tuple[float, float],
        block_size_m: float = 25.0,
        parameters: Optional[List[str]] = None,
    ) -> List[BlockNode]:
        """Generate a full 3D block model over a specified grid extent.

        Args:
            composites: Drill hole composite data.
            east_range: (min_easting, max_easting) of block model extent (metres).
            north_range: (min_northing, max_northing).
            depth_range: (min_depth, max_depth).
            block_size_m: Block dimension (same in all directions). Default 25 m.
            parameters: Grade parameters to estimate. None = all available.

        Returns:
            List of BlockNode objects, one per block in the grid. Blocks with
            insufficient surrounding samples have empty ``estimated_grades``.

        Raises:
            ValueError: If ranges are invalid or block_size_m ≤ 0.
        """
        if block_size_m <= 0:
            raise ValueError(f"block_size_m must be > 0, got {block_size_m}.")

        for label, (lo, hi) in [
            ("east", east_range), ("north", north_range), ("depth", depth_range)
        ]:
            if lo >= hi:
                raise ValueError(
                    f"{label}_range must have min < max, got ({lo}, {hi})."
                )

        blocks: List[BlockNode] = []
        half = block_size_m / 2

        e = east_range[0] + half
        while e <= east_range[1]:
            n = north_range[0] + half
            while n <= north_range[1]:
                d = depth_range[0] + half
                while d <= depth_range[1]:
                    bid = f"E{e:.0f}_N{n:.0f}_D{d:.0f}"
                    block = self.estimate_block(bid, e, n, d, composites, parameters)
                    blocks.append(block)
                    d += block_size_m
                n += block_size_m
            e += block_size_m

        return blocks

    def model_statistics(
        self,
        blocks: List[BlockNode],
        parameter: str,
    ) -> Dict:
        """Calculate summary statistics for a grade parameter across all estimated blocks.

        Only blocks that have a valid estimate for the parameter are included.

        Args:
            blocks: List of BlockNode objects from ``generate_model()``.
            parameter: Grade parameter name.

        Returns:
            Dict with ``mean``, ``min``, ``max``, ``std``, ``estimated_count``,
            ``unestimated_count``.
        """
        values = [
            b.estimated_grades[parameter]
            for b in blocks
            if parameter in b.estimated_grades
        ]
        unestimated = len(blocks) - len(values)

        if not values:
            return {
                "mean": None,
                "min": None,
                "max": None,
                "std": None,
                "estimated_count": 0,
                "unestimated_count": len(blocks),
            }

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)

        return {
            "mean": round(mean, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "std": round(std, 4),
            "estimated_count": len(values),
            "unestimated_count": unestimated,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _distance(
        e1: float, n1: float, d1: float,
        e2: float, n2: float, d2: float,
    ) -> float:
        """3D Euclidean distance between two points."""
        return math.sqrt((e1 - e2) ** 2 + (n1 - n2) ** 2 + (d1 - d2) ** 2)
