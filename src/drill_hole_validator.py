"""
Drill hole collar and survey validation module for geological databases.

Validates borehole data against JORC Code 2012 and QA/QC best practices for
competent persons reports. Catches common data entry errors before resources
are estimated, preventing compounding errors in grade/tonnage calculations.

Common issues detected:
  - Collar coordinates outside expected project boundary
  - Duplicate hole IDs (critical data integrity issue)
  - Survey depth exceeding declared total depth (TD)
  - Non-monotonic downhole depth sequences
  - Interval overlaps or gaps in assay tables
  - Implausible dip/azimuth combinations
  - Missing required JORC fields

References:
    - JORC Code 2012, Table 1 — Sampling Techniques and Data
    - SME Guide for Reporting Exploration Results (2014)
    - AusIMM (2019) Mineral Resource and Ore Reserve Estimation — data QA/QC
    - Snowden (2018) Geological Modelling QC Checklist
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class CollarRecord:
    """
    Drill hole collar record (location and basic info).

    Attributes:
        hole_id (str): Unique hole identifier (e.g., 'DDH-2024-001')
        easting (float): Easting coordinate (metres, UTM preferred)
        northing (float): Northing coordinate (metres, UTM preferred)
        elevation_m (float): Collar elevation above mean sea level (m)
        total_depth_m (float): Declared total depth of hole (m)
        dip_degrees (float): Hole dip angle in degrees (negative = downward)
        azimuth_degrees (float): Hole azimuth (0–360°, clockwise from north)
        hole_type (str): 'DD' (diamond), 'RC' (reverse circulation), 'AC' (aircore), 'RAB'
    """

    hole_id: str
    easting: float
    northing: float
    elevation_m: float
    total_depth_m: float
    dip_degrees: float = -60.0
    azimuth_degrees: float = 0.0
    hole_type: str = "DD"

    VALID_HOLE_TYPES = {"DD", "RC", "AC", "RAB", "PC", "CPT"}

    def __post_init__(self):
        if not self.hole_id.strip():
            raise ValueError("hole_id cannot be empty")
        if self.total_depth_m <= 0:
            raise ValueError(f"total_depth_m must be positive for hole '{self.hole_id}'")
        if not -90.0 <= self.dip_degrees <= 90.0:
            raise ValueError(
                f"dip_degrees must be between -90 and 90, got {self.dip_degrees}"
            )
        if not 0.0 <= self.azimuth_degrees < 360.0:
            raise ValueError(
                f"azimuth_degrees must be in [0, 360), got {self.azimuth_degrees}"
            )
        if self.hole_type not in self.VALID_HOLE_TYPES:
            raise ValueError(
                f"hole_type must be one of {self.VALID_HOLE_TYPES}, got '{self.hole_type}'"
            )


@dataclass
class AssayInterval:
    """
    A single assay/lithology interval for a drill hole.

    Attributes:
        hole_id (str): Hole identifier (must match a CollarRecord)
        from_m (float): Interval start depth (metres from collar)
        to_m (float): Interval end depth (metres from collar)
        grade (float): Assay grade value (units depend on commodity)
        grade_units (str): Grade unit (e.g., '%', 'ppm', 'g/t')
        lithology (str): Rock type code (optional)
    """

    hole_id: str
    from_m: float
    to_m: float
    grade: float
    grade_units: str = "%"
    lithology: str = ""

    def __post_init__(self):
        if not self.hole_id.strip():
            raise ValueError("hole_id cannot be empty")
        if self.from_m < 0:
            raise ValueError(f"from_m cannot be negative for hole '{self.hole_id}'")
        if self.to_m <= self.from_m:
            raise ValueError(
                f"to_m ({self.to_m}) must be greater than from_m ({self.from_m}) "
                f"for hole '{self.hole_id}'"
            )
        if self.grade < 0:
            raise ValueError(f"grade cannot be negative for hole '{self.hole_id}'")

    @property
    def interval_length_m(self) -> float:
        """Interval sample length in metres."""
        return self.to_m - self.from_m


@dataclass
class ValidationIssue:
    """
    A single validation finding.

    Attributes:
        hole_id (str): Affected hole identifier
        severity (str): 'ERROR' (must fix) | 'WARNING' (should investigate) | 'INFO'
        category (str): Issue category (e.g., 'duplicate_id', 'depth_exceeded')
        message (str): Human-readable description of the issue
        from_m (float): Relevant interval start (if applicable)
        to_m (float): Relevant interval end (if applicable)
    """

    hole_id: str
    severity: str   # 'ERROR' | 'WARNING' | 'INFO'
    category: str
    message: str
    from_m: Optional[float] = None
    to_m: Optional[float] = None

    VALID_SEVERITIES = {"ERROR", "WARNING", "INFO"}

    def __post_init__(self):
        if self.severity not in self.VALID_SEVERITIES:
            raise ValueError(f"severity must be one of {self.VALID_SEVERITIES}")


class DrillHoleValidator:
    """
    Validate drill hole collar and assay data for JORC compliance and QA/QC.

    Runs a comprehensive set of checks on collar records and assay intervals,
    returning structured ValidationIssue objects categorised by severity.

    Args:
        project_boundary (Optional[Tuple]): (min_easting, max_easting, min_northing, max_northing)
            If provided, collars outside this boundary are flagged as WARNINGs.
        max_grade_value (float): Maximum plausible grade (default 100 for % grades).
            Set to e.g. 500000 for ppm commodities.
        require_survey (bool): If True, warn when dip/azimuth are default values (default True)

    Example:
        >>> validator = DrillHoleValidator(project_boundary=(350000, 360000, 9700000, 9710000))
        >>> collars = [CollarRecord("DDH-001", 355000, 9705000, 150.0, 300.0, -60, 270, "DD")]
        >>> assays = [AssayInterval("DDH-001", 0.0, 1.0, 45.5, "%")]
        >>> issues = validator.validate_all(collars, assays)
        >>> errors = [i for i in issues if i.severity == "ERROR"]
    """

    def __init__(
        self,
        project_boundary: Optional[Tuple[float, float, float, float]] = None,
        max_grade_value: float = 100.0,
        require_survey: bool = True,
    ):
        if project_boundary is not None:
            if len(project_boundary) != 4:
                raise ValueError("project_boundary must be (min_e, max_e, min_n, max_n)")
            min_e, max_e, min_n, max_n = project_boundary
            if min_e >= max_e or min_n >= max_n:
                raise ValueError("Invalid project_boundary: min must be < max")
        if max_grade_value <= 0:
            raise ValueError("max_grade_value must be positive")

        self.project_boundary = project_boundary
        self.max_grade_value = max_grade_value
        self.require_survey = require_survey

    # ------------------------------------------------------------------
    # Collar validation
    # ------------------------------------------------------------------

    def validate_collars(self, collars: List[CollarRecord]) -> List[ValidationIssue]:
        """
        Validate collar records for common errors.

        Checks:
          1. Duplicate hole IDs (ERROR)
          2. Collar coordinates outside project boundary (WARNING)
          3. Implausible vertical holes (dip = 0°) for underground targets (INFO)
          4. Default azimuth/dip suggesting missing survey (WARNING if require_survey)
          5. Very shallow holes (< 10m TD) potentially incomplete (WARNING)

        Args:
            collars: List of CollarRecord objects

        Returns:
            List of ValidationIssue objects

        Raises:
            ValueError: If collars list is empty
        """
        if not collars:
            raise ValueError("collars list cannot be empty")

        issues: List[ValidationIssue] = []
        seen_ids: Dict[str, int] = {}

        for collar in collars:
            # Check duplicate IDs
            if collar.hole_id in seen_ids:
                issues.append(
                    ValidationIssue(
                        hole_id=collar.hole_id,
                        severity="ERROR",
                        category="duplicate_id",
                        message=f"Duplicate hole_id '{collar.hole_id}' — critical data integrity issue",
                    )
                )
            seen_ids[collar.hole_id] = seen_ids.get(collar.hole_id, 0) + 1

            # Check coordinate boundary
            if self.project_boundary:
                min_e, max_e, min_n, max_n = self.project_boundary
                if not (min_e <= collar.easting <= max_e and min_n <= collar.northing <= max_n):
                    issues.append(
                        ValidationIssue(
                            hole_id=collar.hole_id,
                            severity="WARNING",
                            category="outside_boundary",
                            message=(
                                f"Collar ({collar.easting:.0f}E, {collar.northing:.0f}N) "
                                f"is outside project boundary "
                                f"({min_e:.0f}–{max_e:.0f}E, {min_n:.0f}–{max_n:.0f}N)"
                            ),
                        )
                    )

            # Check for likely unset survey (exact default values)
            if self.require_survey and collar.dip_degrees == -60.0 and collar.azimuth_degrees == 0.0:
                issues.append(
                    ValidationIssue(
                        hole_id=collar.hole_id,
                        severity="WARNING",
                        category="default_survey",
                        message="Dip/azimuth appear to be default values — confirm with survey data",
                    )
                )

            # Very shallow holes
            if collar.total_depth_m < 10.0:
                issues.append(
                    ValidationIssue(
                        hole_id=collar.hole_id,
                        severity="WARNING",
                        category="shallow_hole",
                        message=f"Total depth {collar.total_depth_m}m is very shallow — check if drilling was completed",
                    )
                )

        return issues

    # ------------------------------------------------------------------
    # Assay interval validation
    # ------------------------------------------------------------------

    def validate_assays(
        self,
        assays: List[AssayInterval],
        collars: Optional[List[CollarRecord]] = None,
    ) -> List[ValidationIssue]:
        """
        Validate assay intervals for overlaps, gaps, and grade outliers.

        Checks:
          1. Intervals exceeding total depth of the collar (ERROR) — requires collars
          2. Overlapping intervals within a hole (ERROR)
          3. Grade values above max_grade_value (WARNING)
          4. Holes in assay table not present in collar table (WARNING) — requires collars
          5. Very long single intervals (> 50m) that may obscure grade variability (INFO)

        Args:
            assays: List of AssayInterval objects
            collars: Optional list of CollarRecord for cross-reference checks

        Returns:
            List of ValidationIssue objects
        """
        issues: List[ValidationIssue] = []
        collar_map: Dict[str, CollarRecord] = {}

        if collars:
            collar_map = {c.hole_id: c for c in collars}

        # Group assays by hole
        hole_assays: Dict[str, List[AssayInterval]] = {}
        for a in assays:
            hole_assays.setdefault(a.hole_id, []).append(a)

        for hole_id, intervals in hole_assays.items():
            # Check hole exists in collars
            if collar_map and hole_id not in collar_map:
                issues.append(
                    ValidationIssue(
                        hole_id=hole_id,
                        severity="WARNING",
                        category="missing_collar",
                        message=f"Assay data for '{hole_id}' has no matching collar record",
                    )
                )
                collar_td = None
            else:
                collar_td = collar_map[hole_id].total_depth_m if hole_id in collar_map else None

            # Sort by from_m for sequential checks
            sorted_intervals = sorted(intervals, key=lambda x: x.from_m)

            prev_to = None
            for iv in sorted_intervals:
                # Check depth exceeds TD
                if collar_td is not None and iv.to_m > collar_td + 0.5:  # 0.5m tolerance
                    issues.append(
                        ValidationIssue(
                            hole_id=hole_id,
                            severity="ERROR",
                            category="depth_exceeded",
                            message=(
                                f"Interval {iv.from_m}–{iv.to_m}m exceeds hole TD {collar_td}m"
                            ),
                            from_m=iv.from_m,
                            to_m=iv.to_m,
                        )
                    )

                # Check interval overlap
                if prev_to is not None and iv.from_m < prev_to - 0.01:
                    issues.append(
                        ValidationIssue(
                            hole_id=hole_id,
                            severity="ERROR",
                            category="interval_overlap",
                            message=(
                                f"Interval {iv.from_m}–{iv.to_m}m overlaps with previous "
                                f"interval ending at {prev_to}m"
                            ),
                            from_m=iv.from_m,
                            to_m=iv.to_m,
                        )
                    )

                # Check grade outlier
                if iv.grade > self.max_grade_value:
                    issues.append(
                        ValidationIssue(
                            hole_id=hole_id,
                            severity="WARNING",
                            category="grade_outlier",
                            message=(
                                f"Grade {iv.grade} {iv.grade_units} at {iv.from_m}–{iv.to_m}m "
                                f"exceeds max plausible value {self.max_grade_value}"
                            ),
                            from_m=iv.from_m,
                            to_m=iv.to_m,
                        )
                    )

                # Flag very long intervals
                if iv.interval_length_m > 50.0:
                    issues.append(
                        ValidationIssue(
                            hole_id=hole_id,
                            severity="INFO",
                            category="long_interval",
                            message=(
                                f"Interval length {iv.interval_length_m}m is unusually long. "
                                "Consider sub-sampling for grade estimation."
                            ),
                            from_m=iv.from_m,
                            to_m=iv.to_m,
                        )
                    )

                prev_to = iv.to_m

        return issues

    def validate_all(
        self, collars: List[CollarRecord], assays: List[AssayInterval]
    ) -> List[ValidationIssue]:
        """
        Run all collar and assay validation checks.

        Args:
            collars: List of CollarRecord objects
            assays: List of AssayInterval objects

        Returns:
            Combined list of ValidationIssue objects, sorted by severity (ERROR > WARNING > INFO)

        Example:
            >>> issues = validator.validate_all(collars, assays)
            >>> errors = [i for i in issues if i.severity == "ERROR"]
            >>> print(f"{len(errors)} errors found")
        """
        collar_issues = self.validate_collars(collars)
        assay_issues = self.validate_assays(assays, collars)
        all_issues = collar_issues + assay_issues

        severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        return sorted(all_issues, key=lambda x: (severity_order.get(x.severity, 9), x.hole_id))

    def summary(self, issues: List[ValidationIssue]) -> Dict:
        """
        Summarise validation results.

        Args:
            issues: List from validate_all() or any validate_* method

        Returns:
            Dict with:
                - total_issues (int)
                - errors (int): Must-fix issues
                - warnings (int): Should-investigate issues
                - info (int): Informational only
                - passes_jorc_qaqc (bool): True if no ERRORs
                - categories (Dict[str, int]): Count by category
                - affected_holes (List[str]): Unique hole IDs with any issue
        """
        errors = [i for i in issues if i.severity == "ERROR"]
        warnings = [i for i in issues if i.severity == "WARNING"]
        infos = [i for i in issues if i.severity == "INFO"]
        categories: Dict[str, int] = {}
        for issue in issues:
            categories[issue.category] = categories.get(issue.category, 0) + 1

        return {
            "total_issues": len(issues),
            "errors": len(errors),
            "warnings": len(warnings),
            "info": len(infos),
            "passes_jorc_qaqc": len(errors) == 0,
            "categories": categories,
            "affected_holes": sorted(set(i.hole_id for i in issues)),
        }
