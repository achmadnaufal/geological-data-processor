"""
Variogram Model Fitter for geostatistical grade estimation in coal deposits.

A variogram (semi-variogram) is the foundational tool of geostatistics. It
quantifies spatial grade continuity — how similar two sample grades are as a
function of distance and direction (lag). Fitting a model to the experimental
variogram is a prerequisite for kriging (ordinary kriging, simple kriging, etc.)

Supported theoretical variogram models:
  - Spherical: most common; reaches sill at finite range
  - Exponential: reaches sill asymptotically; better for gradual transitions
  - Gaussian: smooth parabolic near origin; use with care (instability risk)
  - Nugget-only: pure random noise model (no spatial continuity)

Variogram components:
  - Nugget (C0): variance at zero lag (measurement error + microscale variability)
  - Sill (C): total variance plateau (nugget + partial sill)
  - Range (a): distance at which spatial correlation is lost

Applications:
  - Input to Ordinary Kriging (OK) for JORC-compliant resource estimation
  - Spatial continuity analysis for drill-hole spacing optimisation
  - Anisotropy characterisation (major / minor axis range ratio)

References:
  - Isaaks & Srivastava (1989) Applied Geostatistics
  - Deutsch & Journel (1997) GSLIB: Geostatistical Software Library, 2nd Ed.
  - JORC Code 2012: Competent Person requirements for geostatistical methods

Author: github.com/achmadnaufal
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class VariogramModelType(str, Enum):
    """Theoretical variogram model type."""
    SPHERICAL = "spherical"
    EXPONENTIAL = "exponential"
    GAUSSIAN = "gaussian"
    NUGGET_ONLY = "nugget_only"


@dataclass
class ExperimentalVariogramPoint:
    """A single experimental variogram point computed from sample pairs.

    Attributes:
        lag_distance: Centre of the lag class (metres).
        gamma: Experimental semi-variance value at this lag.
        num_pairs: Number of sample pairs contributing to this point.
        lag_tolerance: Half-width of lag class (metres).
    """

    lag_distance: float
    gamma: float
    num_pairs: int
    lag_tolerance: float = 25.0

    def __post_init__(self) -> None:
        if self.lag_distance < 0:
            raise ValueError("lag_distance cannot be negative")
        if self.gamma < 0:
            raise ValueError("gamma (semi-variance) cannot be negative")
        if self.num_pairs <= 0:
            raise ValueError("num_pairs must be positive")


@dataclass
class VariogramModel:
    """Fitted theoretical variogram model parameters.

    Attributes:
        model_type: Theoretical model (spherical, exponential, gaussian).
        nugget: Nugget variance (C0). Must be ≥ 0.
        partial_sill: Partial sill (C). Total sill = nugget + partial_sill.
        range_m: Range of spatial correlation (metres).
        nugget_to_sill_ratio: C0/(C0+C) — measure of relative nugget effect.
        anisotropy_ratio: Range major axis / range minor axis. 1.0 = isotropic.
        anisotropy_azimuth_deg: Azimuth of major continuity axis (°, from North).
        rmse: Root mean square error of model fit to experimental variogram.
    """

    model_type: VariogramModelType
    nugget: float
    partial_sill: float
    range_m: float
    nugget_to_sill_ratio: float = field(init=False)
    anisotropy_ratio: float = 1.0
    anisotropy_azimuth_deg: float = 0.0
    rmse: float = 0.0

    def __post_init__(self) -> None:
        if self.nugget < 0:
            raise ValueError("nugget cannot be negative")
        if self.partial_sill < 0:
            raise ValueError("partial_sill cannot be negative")
        if self.range_m <= 0:
            raise ValueError("range_m must be positive")
        if self.anisotropy_ratio < 1.0:
            raise ValueError("anisotropy_ratio must be ≥ 1.0 (major/minor)")
        total_sill = self.nugget + self.partial_sill
        self.nugget_to_sill_ratio = round(self.nugget / total_sill, 4) if total_sill > 0 else 0.0

    @property
    def total_sill(self) -> float:
        """Total sill = nugget + partial sill."""
        return self.nugget + self.partial_sill

    def gamma_at(self, h: float) -> float:
        """Compute theoretical semi-variance at lag distance h.

        Args:
            h: Lag distance (metres). Must be ≥ 0.

        Returns:
            Theoretical semi-variance γ(h).

        Raises:
            ValueError: If h < 0.
        """
        if h < 0:
            raise ValueError(f"lag distance h must be ≥ 0; got {h}")
        if h == 0:
            return 0.0

        C0 = self.nugget
        C = self.partial_sill
        a = self.range_m

        if self.model_type == VariogramModelType.NUGGET_ONLY:
            return C0

        if self.model_type == VariogramModelType.SPHERICAL:
            if h >= a:
                return C0 + C
            r = h / a
            return C0 + C * (1.5 * r - 0.5 * r ** 3)

        elif self.model_type == VariogramModelType.EXPONENTIAL:
            return C0 + C * (1 - math.exp(-3 * h / a))

        elif self.model_type == VariogramModelType.GAUSSIAN:
            return C0 + C * (1 - math.exp(-3 * (h / a) ** 2))

        return C0 + C  # fallback: return sill

    @property
    def nugget_effect_classification(self) -> str:
        """Classify nugget effect as a ratio of total sill."""
        r = self.nugget_to_sill_ratio
        if r < 0.1:
            return "very_low"   # strong spatial structure
        elif r < 0.25:
            return "low"
        elif r < 0.5:
            return "moderate"
        elif r < 0.75:
            return "high"
        else:
            return "very_high"  # poor spatial correlation


@dataclass
class VariogramFitResult:
    """Result of fitting a theoretical model to experimental variogram data.

    Attributes:
        parameter: Grade parameter this variogram describes.
        model: Fitted VariogramModel.
        experimental_points: Input experimental variogram data.
        residuals: Per-point difference (model - experimental).
        rmse: Root mean square fitting error.
        r_squared: Coefficient of determination for the model fit.
        fit_quality: 'GOOD' / 'ACCEPTABLE' / 'POOR' based on RMSE and R².
        recommendations: Geostatistical recommendations for kriging use.
    """

    parameter: str
    model: VariogramModel
    experimental_points: List[ExperimentalVariogramPoint]
    residuals: List[float]
    rmse: float
    r_squared: float
    fit_quality: str
    recommendations: List[str]


class VariogramModelFitter:
    """Fits theoretical variogram models to experimental semi-variogram data.

    Supports spherical, exponential, and Gaussian models with automatic
    fit quality assessment and kriging recommendations.

    Example:
        >>> fitter = VariogramModelFitter()
        >>> experimental = [
        ...     ExperimentalVariogramPoint(25, 0.12, 45),
        ...     ExperimentalVariogramPoint(50, 0.25, 80),
        ...     ExperimentalVariogramPoint(100, 0.45, 120),
        ...     ExperimentalVariogramPoint(150, 0.58, 95),
        ...     ExperimentalVariogramPoint(200, 0.65, 78),
        ...     ExperimentalVariogramPoint(250, 0.65, 52),
        ... ]
        >>> model = VariogramModel(
        ...     model_type=VariogramModelType.SPHERICAL,
        ...     nugget=0.05, partial_sill=0.60, range_m=200,
        ... )
        >>> result = fitter.fit(experimental, model, parameter="ash_pct")
        >>> print(result.fit_quality)
        'GOOD'
    """

    def __init__(
        self,
        good_rmse_threshold: float = 0.05,
        acceptable_rmse_threshold: float = 0.15,
        min_pairs_per_lag: int = 30,
    ) -> None:
        """Initialise the fitter.

        Args:
            good_rmse_threshold: RMSE below this = GOOD fit.
            acceptable_rmse_threshold: RMSE below this = ACCEPTABLE fit.
            min_pairs_per_lag: Minimum pairs for a lag to be considered reliable.
        """
        self.good_rmse_threshold = good_rmse_threshold
        self.acceptable_rmse_threshold = acceptable_rmse_threshold
        self.min_pairs_per_lag = min_pairs_per_lag

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fit(
        self,
        experimental: List[ExperimentalVariogramPoint],
        model: VariogramModel,
        parameter: str = "grade",
    ) -> VariogramFitResult:
        """Assess the fit of a theoretical model to experimental variogram points.

        Args:
            experimental: List of ExperimentalVariogramPoint data.
            model: Theoretical VariogramModel to evaluate.
            parameter: Name of the grade parameter (for output labelling).

        Returns:
            VariogramFitResult with RMSE, R², fit quality, and recommendations.

        Raises:
            TypeError: If experimental points are not correct type.
            ValueError: If experimental list is empty.
        """
        if not experimental:
            raise ValueError("experimental variogram points cannot be empty")
        if not isinstance(model, VariogramModel):
            raise TypeError("model must be a VariogramModel instance")

        # Filter to reliable lags
        reliable = [p for p in experimental if p.num_pairs >= self.min_pairs_per_lag]
        if not reliable:
            reliable = experimental  # fall back to all if none meet threshold

        gammas_exp = [p.gamma for p in reliable]
        gammas_model = [model.gamma_at(p.lag_distance) for p in reliable]

        residuals = [round(m - e, 6) for m, e in zip(gammas_model, gammas_exp)]
        rmse = math.sqrt(sum(r ** 2 for r in residuals) / len(residuals))

        mean_exp = sum(gammas_exp) / len(gammas_exp)
        ss_tot = sum((e - mean_exp) ** 2 for e in gammas_exp)
        ss_res = sum(r ** 2 for r in residuals)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        fit_quality = self._classify_fit(rmse, r_squared)
        recommendations = self._generate_recommendations(model, reliable, fit_quality, parameter)

        return VariogramFitResult(
            parameter=parameter,
            model=model,
            experimental_points=reliable,
            residuals=residuals,
            rmse=round(rmse, 6),
            r_squared=round(r_squared, 4),
            fit_quality=fit_quality,
            recommendations=recommendations,
        )

    def select_best_model(
        self,
        experimental: List[ExperimentalVariogramPoint],
        candidate_models: List[VariogramModel],
        parameter: str = "grade",
    ) -> VariogramFitResult:
        """Select the best-fitting model from a list of candidates.

        Args:
            experimental: Experimental variogram data.
            candidate_models: List of VariogramModel instances to evaluate.
            parameter: Grade parameter label.

        Returns:
            VariogramFitResult for the best-fitting model (lowest RMSE).

        Raises:
            ValueError: If candidate_models is empty.
        """
        if not candidate_models:
            raise ValueError("candidate_models cannot be empty")

        results = [self.fit(experimental, m, parameter) for m in candidate_models]
        return min(results, key=lambda r: r.rmse)

    def drill_spacing_recommendation(self, model: VariogramModel) -> Dict:
        """Estimate recommended drill hole spacing from variogram range.

        Drill spacing for resource classification:
          - Measured: spacing ≤ range / 2
          - Indicated: spacing ≤ range
          - Inferred: spacing ≤ 2 × range

        Args:
            model: Fitted VariogramModel.

        Returns:
            Dict with recommended spacings for JORC resource categories.
        """
        if not isinstance(model, VariogramModel):
            raise TypeError("model must be a VariogramModel instance")

        return {
            "variogram_range_m": model.range_m,
            "model_type": model.model_type.value,
            "jorc_measured_max_spacing_m": model.range_m / 2,
            "jorc_indicated_max_spacing_m": model.range_m,
            "jorc_inferred_max_spacing_m": model.range_m * 2,
            "note": "Spacings are approximate; JORC Competent Person judgement required.",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_fit(self, rmse: float, r_squared: float) -> str:
        if rmse <= self.good_rmse_threshold and r_squared >= 0.85:
            return "GOOD"
        elif rmse <= self.acceptable_rmse_threshold and r_squared >= 0.70:
            return "ACCEPTABLE"
        else:
            return "POOR"

    def _generate_recommendations(
        self,
        model: VariogramModel,
        reliable_points: List[ExperimentalVariogramPoint],
        fit_quality: str,
        parameter: str,
    ) -> List[str]:
        recs: List[str] = []

        if fit_quality == "POOR":
            recs.append(
                f"Poor variogram fit for '{parameter}' — do not use this model for kriging. "
                "Try alternative model type or adjust sill/range parameters."
            )
        elif fit_quality == "ACCEPTABLE":
            recs.append(
                f"Acceptable fit for '{parameter}'. Validate kriging estimates with cross-validation "
                "before finalising resource classification."
            )

        if model.nugget_effect_classification in ("high", "very_high"):
            recs.append(
                f"High nugget-to-sill ratio ({model.nugget_to_sill_ratio:.2f}): "
                "significant short-scale variability or measurement error. "
                "Review composite length and sampling protocol."
            )

        max_lag = max(p.lag_distance for p in reliable_points) if reliable_points else 0
        if max_lag < model.range_m * 1.5:
            recs.append(
                f"Experimental variogram does not extend to 1.5× range ({model.range_m:.0f}m). "
                "Consider drilling additional holes at greater spacing to confirm range."
            )

        low_pairs = [p for p in reliable_points if p.num_pairs < self.min_pairs_per_lag * 2]
        if low_pairs:
            recs.append(
                f"{len(low_pairs)} lag class(es) have <{self.min_pairs_per_lag * 2} pairs — "
                "consider merging lag classes for more robust experimental variogram."
            )

        if not recs:
            recs.append(
                f"Variogram model for '{parameter}' is well-fitted and suitable for ordinary kriging."
            )

        return recs
