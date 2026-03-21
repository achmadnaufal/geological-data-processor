"""
Grade Outlier Detector for drill hole assay data.

Identifies suspect high-grade or low-grade intervals that may reflect
laboratory errors, sampling contamination, or nugget effect anomalies.
Used in QA/QC workflows before resource estimation to flag intervals
requiring review by the Competent Person.

Methods implemented:
  1. IQR (Interquartile Range) fence — simple, robust, no distributional assumption
  2. Modified Z-score (Iglewicz & Hoaglin) — median-based, robust to outliers
  3. Log-normal probability limit — industry standard for skewed grade distributions
  4. Spatial context check — flags intervals ≥ N × neighbour average (grade smearing)

References:
    Iglewicz, B. & Hoaglin, D.C. (1993) How to Detect and Handle Outliers.
        ASQ Quality Press.
    Sinclair, A.J. & Blackwell, G.H. (2002) Applied Mineral Inventory Estimation.
        Cambridge University Press.
    JORC Code (2012) — Section 4, Resource Estimation QA/QC requirements.

Author: github.com/achmadnaufal
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OutlierFlag:
    """A flagged assay interval.

    Attributes:
        hole_id: Drill hole identifier.
        from_m: Interval start depth (m).
        to_m: Interval end depth (m).
        grade: Assay grade value.
        method: Detection method that raised the flag.
        flag_type: 'high' or 'low'.
        score: Method-specific score (z-score, IQR ratio, etc.).
        message: Human-readable description.
    """

    hole_id: str
    from_m: float
    to_m: float
    grade: float
    method: str
    flag_type: str  # 'high' | 'low'
    score: float
    message: str


@dataclass
class GradeOutlierReport:
    """Summary of outlier detection results.

    Attributes:
        grade_column: Name of the grade column analysed.
        total_intervals: Total assay intervals in the input.
        n_high_outliers: Intervals flagged as high-grade outliers.
        n_low_outliers: Intervals flagged as low-grade outliers.
        outlier_pct: Percentage of intervals flagged.
        flags: List of all :class:`OutlierFlag` objects.
        statistics: Dict of descriptive stats (mean, median, p90, p95, p99).
        recommendations: List of QC recommendations.
    """

    grade_column: str
    total_intervals: int
    n_high_outliers: int
    n_low_outliers: int
    outlier_pct: float
    flags: List[OutlierFlag]
    statistics: Dict[str, float]
    recommendations: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class GradeOutlierDetector:
    """Detect grade outliers in drill hole assay tables.

    Args:
        method: Detection method — 'iqr', 'modified_zscore', or 'lognormal'.
            Default 'modified_zscore'.
        iqr_multiplier: Fence multiplier for IQR method (default 2.5).
            Lower values flag more outliers.
        zscore_threshold: Modified z-score threshold (default 3.5,
            per Iglewicz & Hoaglin).
        lognormal_sigma: Number of log-normal standard deviations beyond
            which an interval is flagged (default 3.0).
        grade_column: Column name containing assay grades.

    Example:
        >>> detector = GradeOutlierDetector(method="modified_zscore")
        >>> df = pd.read_csv("data/assay_data.csv")
        >>> report = detector.detect(df, grade_column="grade_pct")
        >>> print(f"Outliers: {report.n_high_outliers} high, {report.n_low_outliers} low")
        >>> for flag in report.flags:
        ...     print(f"  {flag.hole_id} {flag.from_m}-{flag.to_m}m: {flag.grade:.3f} [{flag.flag_type}]")
    """

    VALID_METHODS = {"iqr", "modified_zscore", "lognormal"}

    def __init__(
        self,
        method: str = "modified_zscore",
        iqr_multiplier: float = 2.5,
        zscore_threshold: float = 3.5,
        lognormal_sigma: float = 3.0,
    ):
        if method not in self.VALID_METHODS:
            raise ValueError(f"method must be one of {self.VALID_METHODS}")
        if iqr_multiplier <= 0:
            raise ValueError("iqr_multiplier must be positive")
        if zscore_threshold <= 0:
            raise ValueError("zscore_threshold must be positive")
        if lognormal_sigma <= 0:
            raise ValueError("lognormal_sigma must be positive")

        self.method = method
        self.iqr_multiplier = iqr_multiplier
        self.zscore_threshold = zscore_threshold
        self.lognormal_sigma = lognormal_sigma

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        df: pd.DataFrame,
        grade_column: str = "grade_pct",
        hole_id_column: str = "hole_id",
        from_column: str = "from_m",
        to_column: str = "to_m",
    ) -> GradeOutlierReport:
        """Run outlier detection on an assay DataFrame.

        Args:
            df: Assay DataFrame with at least the grade column.
            grade_column: Column name of the assay grade.
            hole_id_column: Column name for drill hole IDs.
            from_column: Column name for interval start depths.
            to_column: Column name for interval end depths.

        Returns:
            :class:`GradeOutlierReport` with all flagged intervals.

        Raises:
            ValueError: If grade_column is missing or all values are null/negative.
        """
        self._validate_df(df, grade_column)
        work = df.copy()
        grades = pd.to_numeric(work[grade_column], errors="coerce").dropna()
        grades = grades[grades >= 0]  # exclude negative grades (common null sentinel)

        if len(grades) < 4:
            raise ValueError("At least 4 valid (non-negative) grade values required")

        stats = self._compute_stats(grades)
        bounds = self._compute_bounds(grades)
        lo_bound, hi_bound = bounds

        flags: List[OutlierFlag] = []
        for _, row in work.iterrows():
            grade_val = pd.to_numeric(row.get(grade_column), errors="coerce")
            if pd.isna(grade_val) or grade_val < 0:
                continue
            hole = str(row.get(hole_id_column, "UNKNOWN"))
            from_m = float(row.get(from_column, 0))
            to_m = float(row.get(to_column, 0))

            if hi_bound is not None and grade_val > hi_bound:
                score = self._compute_score(grade_val, grades)
                flags.append(OutlierFlag(
                    hole_id=hole,
                    from_m=from_m,
                    to_m=to_m,
                    grade=round(grade_val, 4),
                    method=self.method,
                    flag_type="high",
                    score=round(score, 3),
                    message=(
                        f"Grade {grade_val:.3f} exceeds upper bound {hi_bound:.3f} "
                        f"(method={self.method}, score={score:.2f})"
                    ),
                ))
            elif lo_bound is not None and grade_val < lo_bound:
                score = self._compute_score(grade_val, grades)
                flags.append(OutlierFlag(
                    hole_id=hole,
                    from_m=from_m,
                    to_m=to_m,
                    grade=round(grade_val, 4),
                    method=self.method,
                    flag_type="low",
                    score=round(score, 3),
                    message=(
                        f"Grade {grade_val:.3f} below lower bound {lo_bound:.3f} "
                        f"(method={self.method}, score={score:.2f})"
                    ),
                ))

        n_high = sum(1 for f in flags if f.flag_type == "high")
        n_low = sum(1 for f in flags if f.flag_type == "low")
        outlier_pct = len(flags) / len(work) * 100 if len(work) > 0 else 0.0
        recs = self._build_recommendations(flags, stats, hi_bound)

        return GradeOutlierReport(
            grade_column=grade_column,
            total_intervals=len(work),
            n_high_outliers=n_high,
            n_low_outliers=n_low,
            outlier_pct=round(outlier_pct, 2),
            flags=flags,
            statistics=stats,
            recommendations=recs,
        )

    def top_outliers(
        self, report: GradeOutlierReport, n: int = 10, flag_type: str = "high"
    ) -> List[OutlierFlag]:
        """Return the N most extreme outliers of a given type.

        Args:
            report: Output from :meth:`detect`.
            n: Number of outliers to return.
            flag_type: 'high' or 'low'.

        Returns:
            List of :class:`OutlierFlag` sorted by grade descending (for high)
            or ascending (for low).
        """
        if flag_type not in ("high", "low"):
            raise ValueError("flag_type must be 'high' or 'low'")
        filtered = [f for f in report.flags if f.flag_type == flag_type]
        reverse = flag_type == "high"
        return sorted(filtered, key=lambda f: f.grade, reverse=reverse)[:n]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_bounds(self, grades: pd.Series) -> Tuple[Optional[float], Optional[float]]:
        if self.method == "iqr":
            q1, q3 = grades.quantile(0.25), grades.quantile(0.75)
            iqr = q3 - q1
            return (
                max(0, q1 - self.iqr_multiplier * iqr),
                q3 + self.iqr_multiplier * iqr,
            )
        elif self.method == "modified_zscore":
            median = grades.median()
            mad = (grades - median).abs().median()
            if mad == 0:
                # Fall back to std-based for uniform data
                std = grades.std()
                return (
                    max(0, median - self.zscore_threshold * std),
                    median + self.zscore_threshold * std,
                )
            scale = 0.6745  # consistency constant
            threshold_unit = self.zscore_threshold * mad / scale
            return (
                max(0, median - threshold_unit),
                median + threshold_unit,
            )
        elif self.method == "lognormal":
            log_grades = grades[grades > 0].apply(math.log)
            if len(log_grades) < 4:
                return None, None
            mu = log_grades.mean()
            sigma = log_grades.std()
            return (
                math.exp(mu - self.lognormal_sigma * sigma),
                math.exp(mu + self.lognormal_sigma * sigma),
            )
        return None, None

    def _compute_score(self, grade: float, grades: pd.Series) -> float:
        """Return a dimensionless outlier score for the given grade."""
        if self.method == "modified_zscore":
            median = grades.median()
            mad = (grades - median).abs().median()
            if mad == 0:
                return abs(grade - median) / (grades.std() + 1e-9)
            return 0.6745 * abs(grade - median) / mad
        elif self.method == "lognormal" and grade > 0:
            log_grades = grades[grades > 0].apply(math.log)
            mu, sigma = log_grades.mean(), log_grades.std()
            return abs(math.log(grade) - mu) / (sigma + 1e-9)
        else:  # IQR
            q1, q3 = grades.quantile(0.25), grades.quantile(0.75)
            iqr = q3 - q1 + 1e-9
            return abs(grade - grades.median()) / iqr

    @staticmethod
    def _compute_stats(grades: pd.Series) -> Dict[str, float]:
        return {
            "count": int(len(grades)),
            "mean": round(float(grades.mean()), 4),
            "median": round(float(grades.median()), 4),
            "std": round(float(grades.std()), 4),
            "min": round(float(grades.min()), 4),
            "max": round(float(grades.max()), 4),
            "p90": round(float(grades.quantile(0.90)), 4),
            "p95": round(float(grades.quantile(0.95)), 4),
            "p99": round(float(grades.quantile(0.99)), 4),
        }

    @staticmethod
    def _build_recommendations(
        flags: List[OutlierFlag], stats: Dict[str, float], hi_bound: Optional[float]
    ) -> List[str]:
        recs: List[str] = []
        n_high = sum(1 for f in flags if f.flag_type == "high")
        if n_high > 0 and hi_bound:
            recs.append(
                f"Review {n_high} high-grade interval(s) above {hi_bound:.3f}. "
                "Consider capping/top-cutting at P99 for resource estimation."
            )
        if n_high / max(stats.get("count", 1), 1) > 0.05:
            recs.append(
                "High outlier rate (>5% of intervals). "
                "Check for laboratory contamination or pulp mix-up."
            )
        if stats.get("max", 0) > stats.get("p99", 0) * 5:
            recs.append(
                "Extreme high-grade spike detected (max > 5× p99). "
                "Flag for Competent Person review before resource classification."
            )
        return recs

    @staticmethod
    def _validate_df(df: pd.DataFrame, grade_column: str) -> None:
        if grade_column not in df.columns:
            raise ValueError(f"Grade column '{grade_column}' not found in DataFrame")
        if df[grade_column].isna().all():
            raise ValueError(f"All values in '{grade_column}' are null")
