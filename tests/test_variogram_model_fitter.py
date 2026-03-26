"""Unit tests for VariogramModelFitter."""
import pytest
import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from variogram_model_fitter import (
    VariogramModelFitter,
    VariogramModel,
    VariogramModelType,
    ExperimentalVariogramPoint,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_experimental(n_points=6) -> list:
    lags = [25 * (i + 1) for i in range(n_points)]
    gammas = [min(0.65, 0.65 * (1 - math.exp(-3 * lag / 200))) for lag in lags]
    return [ExperimentalVariogramPoint(lag, gamma, 50) for lag, gamma in zip(lags, gammas)]


def make_spherical(nugget=0.05, partial_sill=0.60, range_m=200) -> VariogramModel:
    return VariogramModel(
        model_type=VariogramModelType.SPHERICAL,
        nugget=nugget,
        partial_sill=partial_sill,
        range_m=range_m,
    )


# ---------------------------------------------------------------------------
# ExperimentalVariogramPoint tests
# ---------------------------------------------------------------------------

class TestExperimentalPoint:
    def test_valid_point(self):
        p = ExperimentalVariogramPoint(50, 0.3, 45)
        assert p.lag_distance == 50

    def test_negative_lag_raises(self):
        with pytest.raises(ValueError):
            ExperimentalVariogramPoint(-10, 0.3, 45)

    def test_negative_gamma_raises(self):
        with pytest.raises(ValueError):
            ExperimentalVariogramPoint(50, -0.1, 45)

    def test_zero_pairs_raises(self):
        with pytest.raises(ValueError):
            ExperimentalVariogramPoint(50, 0.3, 0)


# ---------------------------------------------------------------------------
# VariogramModel tests
# ---------------------------------------------------------------------------

class TestVariogramModel:
    def test_total_sill(self):
        m = make_spherical(nugget=0.1, partial_sill=0.5)
        assert abs(m.total_sill - 0.6) < 0.001

    def test_nugget_to_sill_ratio(self):
        m = make_spherical(nugget=0.1, partial_sill=0.5)
        assert abs(m.nugget_to_sill_ratio - (0.1 / 0.6)) < 0.001

    def test_gamma_at_zero(self):
        m = make_spherical()
        assert m.gamma_at(0) == 0.0

    def test_spherical_at_range_equals_sill(self):
        m = make_spherical(nugget=0.05, partial_sill=0.60, range_m=200)
        assert abs(m.gamma_at(200) - m.total_sill) < 0.001

    def test_spherical_beyond_range_equals_sill(self):
        m = make_spherical(nugget=0.05, partial_sill=0.60, range_m=200)
        assert abs(m.gamma_at(500) - m.total_sill) < 0.001

    def test_exponential_approaches_sill(self):
        m = VariogramModel(VariogramModelType.EXPONENTIAL, 0.05, 0.60, 200)
        # At large distance, gamma ≈ sill
        assert abs(m.gamma_at(2000) - m.total_sill) < 0.01

    def test_gaussian_smooth_near_origin(self):
        m = VariogramModel(VariogramModelType.GAUSSIAN, 0.05, 0.60, 200)
        g_small = m.gamma_at(1)
        g_medium = m.gamma_at(50)
        assert g_small < g_medium

    def test_negative_nugget_raises(self):
        with pytest.raises(ValueError):
            VariogramModel(VariogramModelType.SPHERICAL, -0.1, 0.5, 200)

    def test_zero_range_raises(self):
        with pytest.raises(ValueError):
            VariogramModel(VariogramModelType.SPHERICAL, 0.05, 0.5, 0)

    def test_anisotropy_below_1_raises(self):
        with pytest.raises(ValueError):
            VariogramModel(VariogramModelType.SPHERICAL, 0.05, 0.5, 200, anisotropy_ratio=0.5)


# ---------------------------------------------------------------------------
# VariogramModelFitter tests
# ---------------------------------------------------------------------------

class TestVariogramModelFitter:
    def setup_method(self):
        self.fitter = VariogramModelFitter()

    def test_fit_returns_result(self):
        exp = make_experimental()
        model = make_spherical()
        result = self.fitter.fit(exp, model, parameter="ash_pct")
        assert result.rmse >= 0
        assert result.r_squared <= 1.0

    def test_good_fit_exponential(self):
        # Build experimental from exact exponential model
        model = VariogramModel(VariogramModelType.EXPONENTIAL, 0.05, 0.60, 200)
        exp = [ExperimentalVariogramPoint(lag, model.gamma_at(lag), 60) for lag in range(25, 325, 25)]
        result = self.fitter.fit(exp, model, parameter="test")
        assert result.rmse < 0.001
        assert result.fit_quality == "GOOD"

    def test_empty_experimental_raises(self):
        with pytest.raises(ValueError):
            self.fitter.fit([], make_spherical())

    def test_invalid_model_type_raises(self):
        with pytest.raises(TypeError):
            self.fitter.fit(make_experimental(), {"nugget": 0.05})

    def test_select_best_model(self):
        exp = make_experimental()
        models = [
            make_spherical(nugget=0.05, partial_sill=0.60, range_m=200),
            make_spherical(nugget=0.20, partial_sill=0.40, range_m=100),  # worse fit
        ]
        best = self.fitter.select_best_model(exp, models)
        assert best.rmse == min(self.fitter.fit(exp, m).rmse for m in models)

    def test_select_best_empty_raises(self):
        with pytest.raises(ValueError):
            self.fitter.select_best_model(make_experimental(), [])

    def test_drill_spacing_recommendation(self):
        model = make_spherical(range_m=200)
        rec = self.fitter.drill_spacing_recommendation(model)
        assert rec["jorc_measured_max_spacing_m"] == 100.0
        assert rec["jorc_indicated_max_spacing_m"] == 200.0

    def test_drill_spacing_invalid_type_raises(self):
        with pytest.raises(TypeError):
            self.fitter.drill_spacing_recommendation({"range_m": 200})

    def test_recommendations_not_empty(self):
        exp = make_experimental()
        result = self.fitter.fit(exp, make_spherical())
        assert len(result.recommendations) >= 1
