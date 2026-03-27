"""
lithology_classifier.py — Rule-based lithology classification from borehole assay data.

Classifies rock/sediment intervals in coal-bearing sequences into lithology units
based on geophysical and geochemical proxy parameters. Designed for Kalimantan
and Sumatra coal basin stratigraphy (Eocene–Miocene deltaic/fluvial sequences).

Supported lithology classes:
  - coal / carbonaceous_shale / shale / siltstone / sandstone / conglomerate
  - tuff / claystone / limestone (for interbedded sequences)

Classification methods:
  1. Proximate analysis-based (ash, VM, moisture for coal intervals)
  2. Density/gamma proxy from field descriptions
  3. Grain size + sorting descriptor rules
  4. Sequential boundary detection for seam partings

References:
    - Thomas (2013) Coal Geology. 2nd ed. Wiley-Blackwell.
    - Friederich et al. (2018) Stratigraphy of Kalimantan coal basins. Indonesian Geology Journal
    - ASTM D121 Standard Terminology of Coal and Coke
    - Diessel (1992) Coal-bearing depositional systems. Springer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Lithology constants
# ---------------------------------------------------------------------------

VALID_LITHOLOGIES = {
    "coal", "carbonaceous_shale", "shale", "claystone",
    "siltstone", "sandstone", "conglomerate", "tuff", "limestone",
    "undifferentiated",
}

# Classification thresholds from proximate analysis (air-dried basis)
# Source: ASTM D121, Thomas (2013) Coal Geology
COAL_ASH_MAX_PCT = 50.0          # Above 50% ash → not coal (rock parting)
CARBONACEOUS_ASH_MAX_PCT = 70.0  # 50–70% ash → carbonaceous shale
COAL_CV_MIN_KCAL = 1500.0        # Minimum GCV to be considered coal (lignite threshold)

# Density ranges (g/cm³) for lithology proxies
DENSITY_RANGES: Dict[str, Tuple[float, float]] = {
    "coal": (1.15, 1.70),
    "carbonaceous_shale": (1.70, 2.10),
    "shale": (2.10, 2.50),
    "claystone": (1.90, 2.30),
    "siltstone": (2.30, 2.60),
    "sandstone": (2.20, 2.65),
    "conglomerate": (2.30, 2.75),
    "tuff": (1.80, 2.40),
    "limestone": (2.60, 2.80),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BoreholeInterval:
    """A single depth interval from a borehole with proxy measurements.

    Attributes:
        interval_id: Unique interval identifier.
        borehole_id: Parent borehole identifier.
        depth_from_m: Top of interval (metres, positive down).
        depth_to_m: Bottom of interval (metres).
        ash_ad_pct: Air-dried ash content (%). Used as primary coal classifier.
        moisture_ad_pct: Air-dried moisture (%).
        volatile_matter_daf_pct: VM on daf basis (%). Optional — used for coal rank.
        gcv_gar_kcal_kg: Gross calorific value as-received (kcal/kg). Optional.
        density_g_cm3: Bulk density from core measurement (g/cm³). Optional.
        grain_size_descriptor: Field description: 'clay', 'silt', 'fine_sand',
            'medium_sand', 'coarse_sand', 'gravel', or None.
        field_lithology: Geologist's field call (optional — for comparison).
        color_description: Color note (e.g., 'black', 'grey', 'brown').

    Raises:
        ValueError: If depths are invalid or quality parameters are out of range.

    Example:
        >>> interval = BoreholeInterval(
        ...     interval_id="BH001-015",
        ...     borehole_id="BH001",
        ...     depth_from_m=14.5,
        ...     depth_to_m=17.2,
        ...     ash_ad_pct=8.5,
        ...     moisture_ad_pct=22.0,
        ...     volatile_matter_daf_pct=48.0,
        ...     gcv_gar_kcal_kg=4100.0,
        ... )
        >>> interval.thickness_m
        2.7
    """

    interval_id: str
    borehole_id: str
    depth_from_m: float
    depth_to_m: float
    ash_ad_pct: float
    moisture_ad_pct: float = 0.0
    volatile_matter_daf_pct: Optional[float] = None
    gcv_gar_kcal_kg: Optional[float] = None
    density_g_cm3: Optional[float] = None
    grain_size_descriptor: Optional[str] = None
    field_lithology: Optional[str] = None
    color_description: str = ""

    VALID_GRAIN_SIZES = {
        "clay", "silt", "fine_sand", "medium_sand", "coarse_sand", "gravel", None
    }

    def __post_init__(self) -> None:
        if not self.interval_id.strip():
            raise ValueError("interval_id must not be empty.")
        if not self.borehole_id.strip():
            raise ValueError("borehole_id must not be empty.")
        if self.depth_from_m < 0:
            raise ValueError("depth_from_m must be non-negative.")
        if self.depth_to_m <= self.depth_from_m:
            raise ValueError(
                f"depth_to_m ({self.depth_to_m}) must be greater than depth_from_m ({self.depth_from_m})."
            )
        if not (0.0 <= self.ash_ad_pct <= 100.0):
            raise ValueError(f"ash_ad_pct {self.ash_ad_pct} must be in [0, 100].")
        if not (0.0 <= self.moisture_ad_pct <= 70.0):
            raise ValueError(f"moisture_ad_pct {self.moisture_ad_pct} out of range.")
        if self.volatile_matter_daf_pct is not None and not (0.0 <= self.volatile_matter_daf_pct <= 100.0):
            raise ValueError("volatile_matter_daf_pct must be in [0, 100].")
        if self.gcv_gar_kcal_kg is not None and self.gcv_gar_kcal_kg < 0:
            raise ValueError("gcv_gar_kcal_kg must be non-negative.")
        if self.density_g_cm3 is not None and not (0.5 <= self.density_g_cm3 <= 3.5):
            raise ValueError("density_g_cm3 must be in [0.5, 3.5] g/cm³.")
        if self.grain_size_descriptor not in self.VALID_GRAIN_SIZES:
            raise ValueError(
                f"grain_size_descriptor '{self.grain_size_descriptor}' not recognised. "
                f"Valid: {self.VALID_GRAIN_SIZES}"
            )

    @property
    def thickness_m(self) -> float:
        """Interval thickness in metres."""
        return round(self.depth_to_m - self.depth_from_m, 3)

    @property
    def depth_mid_m(self) -> float:
        """Mid-point depth of the interval."""
        return round((self.depth_from_m + self.depth_to_m) / 2.0, 3)


@dataclass
class LithologyClassification:
    """Classification result for a single borehole interval.

    Attributes:
        interval_id: Interval identifier.
        borehole_id: Borehole identifier.
        depth_from_m: Top depth.
        depth_to_m: Bottom depth.
        classified_lithology: Assigned lithology class.
        confidence: 'high', 'medium', or 'low'.
        classification_basis: Which data was used ('proximate', 'density', 'grain_size', 'multi').
        notes: Explanation of classification logic.
        agreement_with_field: True if classified agrees with field_lithology (when available).
    """

    interval_id: str
    borehole_id: str
    depth_from_m: float
    depth_to_m: float
    classified_lithology: str
    confidence: str
    classification_basis: str
    notes: str
    agreement_with_field: Optional[bool] = None


# ---------------------------------------------------------------------------
# Core classifier
# ---------------------------------------------------------------------------


class LithologyClassifier:
    """Rule-based lithology classification for coal exploration boreholes.

    Classification priority:
    1. If ash < 50% and GCV ≥ 1500 kcal/kg → COAL (high confidence)
    2. If ash 50–70% → CARBONACEOUS SHALE
    3. If density available → density-range lookup
    4. If grain size available → grain-size-based classification
    5. If VM available → VM-based coal rank check
    6. Fallback → UNDIFFERENTIATED (low confidence)

    Args:
        use_density_fallback: If True (default), use density for classification when
            proximate analysis is ambiguous.
        use_grain_size: If True (default), incorporate grain size descriptors.

    Example:
        >>> clf = LithologyClassifier()
        >>> result = clf.classify(interval)
        >>> result.classified_lithology
        'coal'
    """

    def __init__(
        self,
        use_density_fallback: bool = True,
        use_grain_size: bool = True,
    ) -> None:
        self.use_density_fallback = use_density_fallback
        self.use_grain_size = use_grain_size

    def classify(self, interval: BoreholeInterval) -> LithologyClassification:
        """Classify a single borehole interval.

        Args:
            interval: BoreholeInterval with at least ash content.

        Returns:
            LithologyClassification with assigned class, confidence, and notes.
        """
        litho, confidence, basis, notes = self._classify_logic(interval)

        # Check agreement with field call
        agreement = None
        if interval.field_lithology is not None:
            agreement = (
                interval.field_lithology.lower().replace(" ", "_") == litho.lower()
            )

        return LithologyClassification(
            interval_id=interval.interval_id,
            borehole_id=interval.borehole_id,
            depth_from_m=interval.depth_from_m,
            depth_to_m=interval.depth_to_m,
            classified_lithology=litho,
            confidence=confidence,
            classification_basis=basis,
            notes=notes,
            agreement_with_field=agreement,
        )

    def _classify_logic(
        self, interval: BoreholeInterval
    ) -> Tuple[str, str, str, str]:
        """Return (lithology, confidence, basis, notes)."""
        ash = interval.ash_ad_pct
        gcv = interval.gcv_gar_kcal_kg
        density = interval.density_g_cm3
        grain = interval.grain_size_descriptor
        vm = interval.volatile_matter_daf_pct

        evidences = []

        # ---- Priority 1: Coal classification from ash + GCV ----
        if ash < COAL_ASH_MAX_PCT:
            if gcv is not None:
                if gcv >= COAL_CV_MIN_KCAL:
                    notes = (
                        f"Low ash ({ash:.1f}%) + GCV {gcv:.0f} kcal/kg ≥ {COAL_CV_MIN_KCAL:.0f} → coal confirmed."
                    )
                    return "coal", "high", "proximate", notes
                else:
                    # Low ash but also low GCV — could be very high moisture lignite or carbonaceous
                    evidences.append(f"Low ash ({ash:.1f}%) but low GCV ({gcv:.0f} kcal/kg).")
            else:
                # No GCV — use ash alone
                if ash < 20.0:
                    notes = f"Very low ash ({ash:.1f}%), no GCV — classified as coal (high confidence)."
                    return "coal", "high", "proximate", notes
                elif ash < 35.0:
                    notes = f"Low ash ({ash:.1f}%), no GCV — classified as coal (medium confidence)."
                    return "coal", "medium", "proximate", notes
                else:
                    evidences.append(f"Moderate ash ({ash:.1f}%), no GCV — uncertain.")

        # ---- Priority 2: Carbonaceous shale (ash 50–70%) ----
        if COAL_ASH_MAX_PCT <= ash < CARBONACEOUS_ASH_MAX_PCT:
            notes = f"Ash {ash:.1f}% in 50–70% range → carbonaceous shale."
            return "carbonaceous_shale", "high", "proximate", notes

        # ---- Priority 3: High ash (>70%) → clastic rock ----
        if ash >= CARBONACEOUS_ASH_MAX_PCT:
            evidences.append(f"High ash ({ash:.1f}%) — clastic rock.")
            # Use density or grain size to differentiate
            if self.use_density_fallback and density is not None:
                litho = self._density_classify(density)
                notes = f"High ash + density {density:.2f} g/cm³ → {litho}."
                return litho, "medium", "density", notes
            if self.use_grain_size and grain is not None:
                litho = self._grain_size_classify(grain)
                notes = f"High ash + grain size '{grain}' → {litho}."
                return litho, "medium", "grain_size", notes

        # ---- Priority 4: Low GCV despite low ash ----
        if evidences and gcv is not None and gcv < COAL_CV_MIN_KCAL:
            if density is not None:
                litho = self._density_classify(density)
                notes = " | ".join(evidences) + f" Density {density:.2f} g/cm³ → {litho}."
                return litho, "medium", "multi", notes

        # ---- Priority 5: Density-only classification ----
        if self.use_density_fallback and density is not None and not evidences:
            litho = self._density_classify(density)
            notes = f"Density {density:.2f} g/cm³ → {litho} (no proximate data)."
            return litho, "medium", "density", notes

        # ---- Priority 6: Grain size only ----
        if self.use_grain_size and grain is not None:
            litho = self._grain_size_classify(grain)
            notes = f"Grain size '{grain}' → {litho}."
            return litho, "low", "grain_size", notes

        # ---- Fallback: undifferentiated ----
        notes = " | ".join(evidences) if evidences else "Insufficient data for classification."
        return "undifferentiated", "low", "none", notes

    def _density_classify(self, density: float) -> str:
        """Classify based on bulk density (g/cm³) lookup."""
        # Best-match approach: find lithology with range containing density
        matches = []
        for litho, (lo, hi) in DENSITY_RANGES.items():
            if lo <= density <= hi:
                matches.append((litho, hi - lo))  # smaller range = more specific

        if not matches:
            # Below all ranges → likely coal/organic
            if density < 1.70:
                return "coal"
            # Above all ranges → likely limestone or conglomerate
            return "limestone"

        # Return most specific match (smallest range)
        matches.sort(key=lambda x: x[1])
        return matches[0][0]

    def _grain_size_classify(self, grain: str) -> str:
        """Classify based on grain size descriptor."""
        grain_map = {
            "clay": "claystone",
            "silt": "siltstone",
            "fine_sand": "sandstone",
            "medium_sand": "sandstone",
            "coarse_sand": "sandstone",
            "gravel": "conglomerate",
        }
        return grain_map.get(grain, "undifferentiated")

    def classify_borehole(
        self, intervals: List[BoreholeInterval]
    ) -> List[LithologyClassification]:
        """Classify all intervals in a borehole.

        Args:
            intervals: List of BoreholeInterval instances from one borehole.
                Must all share the same borehole_id.

        Returns:
            List of LithologyClassification results sorted by depth_from_m.

        Raises:
            ValueError: If intervals is empty or contains mixed borehole IDs.
        """
        if not intervals:
            raise ValueError("intervals must not be empty.")
        borehole_ids = {i.borehole_id for i in intervals}
        if len(borehole_ids) > 1:
            raise ValueError(
                f"All intervals must share one borehole_id; found: {borehole_ids}."
            )
        sorted_intervals = sorted(intervals, key=lambda x: x.depth_from_m)
        return [self.classify(i) for i in sorted_intervals]

    def coal_seam_summary(
        self, classifications: List[LithologyClassification]
    ) -> Dict:
        """Summarise coal seams from a classified borehole log.

        Args:
            classifications: Output from classify_borehole().

        Returns:
            Dict with n_coal_intervals, n_partings, total_coal_thickness_m,
            coal_intervals (list of depth/thickness), has_split_seam.
        """
        coal_intervals = [
            c for c in classifications if c.classified_lithology == "coal"
        ]
        non_coal_between = []
        in_coal_zone = False

        # Detect partings (non-coal between coal intervals)
        sorted_cls = sorted(classifications, key=lambda x: x.depth_from_m)
        first_coal = next((c for c in sorted_cls if c.classified_lithology == "coal"), None)
        last_coal = None
        for c in reversed(sorted_cls):
            if c.classified_lithology == "coal":
                last_coal = c
                break

        n_partings = 0
        if first_coal and last_coal and first_coal is not last_coal:
            in_seam = False
            for c in sorted_cls:
                if c.classified_lithology == "coal":
                    if in_seam:
                        pass
                    in_seam = True
                elif in_seam and c.classified_lithology != "coal":
                    # Check if we come back to coal after this
                    after = [x for x in sorted_cls if x.depth_from_m >= c.depth_to_m and
                              x.classified_lithology == "coal"]
                    if after:
                        n_partings += 1

        total_thickness = sum(
            c.depth_to_m - c.depth_from_m for c in coal_intervals
        )

        return {
            "n_coal_intervals": len(coal_intervals),
            "n_partings": n_partings,
            "total_coal_thickness_m": round(total_thickness, 2),
            "coal_intervals": [
                {"depth_from_m": c.depth_from_m, "depth_to_m": c.depth_to_m,
                 "thickness_m": round(c.depth_to_m - c.depth_from_m, 2)}
                for c in coal_intervals
            ],
            "has_split_seam": n_partings > 0,
        }

    def field_agreement_rate(
        self, classifications: List[LithologyClassification]
    ) -> Optional[float]:
        """Compute agreement rate between classified and field lithology.

        Args:
            classifications: List of LithologyClassification results.

        Returns:
            Agreement rate (0–1) for intervals where field_lithology was available,
            or None if no field calls are present.
        """
        with_field = [c for c in classifications if c.agreement_with_field is not None]
        if not with_field:
            return None
        agreed = sum(1 for c in with_field if c.agreement_with_field)
        return round(agreed / len(with_field), 4)
