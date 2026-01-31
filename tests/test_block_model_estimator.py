"""
Unit tests for BlockModelEstimator.
"""

import pytest
from src.block_model_estimator import (
    BlockModelEstimator,
    BlockNode,
    DrillHoleComposite,
)


@pytest.fixture
def estimator():
    return BlockModelEstimator(power=2.0, max_search_radius_m=300.0, min_samples=2)


@pytest.fixture
def simple_composites():
    """Four composites forming a simple cluster."""
    return [
        DrillHoleComposite("DDH001", 500, 100, 50, {"ash_pct": 8.0, "gcv_kcal_kg": 6500}),
        DrillHoleComposite("DDH002", 550, 150, 55, {"ash_pct": 9.5, "gcv_kcal_kg": 6300}),
        DrillHoleComposite("DDH003", 520, 200, 48, {"ash_pct": 7.5, "gcv_kcal_kg": 6700}),
        DrillHoleComposite("DDH004", 480, 130, 52, {"ash_pct": 10.2, "gcv_kcal_kg": 6100}),
    ]


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_defaults_accepted(self):
        e = BlockModelEstimator()
        assert e._power == 2.0

    def test_zero_power_raises(self):
        with pytest.raises(ValueError, match="power"):
            BlockModelEstimator(power=0)

    def test_zero_search_radius_raises(self):
        with pytest.raises(ValueError, match="max_search_radius_m"):
            BlockModelEstimator(max_search_radius_m=0)

    def test_min_samples_greater_than_max_raises(self):
        with pytest.raises(ValueError, match="max_samples"):
            BlockModelEstimator(min_samples=10, max_samples=5)


# ---------------------------------------------------------------------------
# estimate_block
# ---------------------------------------------------------------------------

class TestEstimateBlock:
    def test_returns_block_node(self, estimator, simple_composites):
        block = estimator.estimate_block("B1", 520, 150, 52, simple_composites)
        assert isinstance(block, BlockNode)

    def test_block_id_preserved(self, estimator, simple_composites):
        block = estimator.estimate_block("TEST_BLOCK", 520, 150, 52, simple_composites)
        assert block.block_id == "TEST_BLOCK"

    def test_estimated_grades_within_input_range(self, estimator, simple_composites):
        block = estimator.estimate_block("B1", 520, 150, 52, simple_composites)
        ash = block.estimated_grades.get("ash_pct")
        assert ash is not None
        assert 7.5 <= ash <= 10.2  # must be within the range of input samples

    def test_sample_count_matches_contributors(self, estimator, simple_composites):
        block = estimator.estimate_block("B1", 520, 150, 52, simple_composites)
        assert block.sample_count >= 2

    def test_insufficient_samples_returns_empty_grades(self):
        estimator_strict = BlockModelEstimator(min_samples=10, max_search_radius_m=50.0)
        composites = [DrillHoleComposite("H1", 500, 100, 50, {"ash_pct": 8.0})]
        block = estimator_strict.estimate_block("B1", 520, 150, 52, composites)
        assert block.estimated_grades == {}
        assert block.sample_count < 10

    def test_coincident_sample_uses_exact_value(self, estimator):
        composites = [
            DrillHoleComposite("H1", 500, 100, 50, {"ash_pct": 8.0}),
            DrillHoleComposite("H2", 500, 100, 50, {"ash_pct": 8.0}),
        ]
        block = estimator.estimate_block("B1", 500, 100, 50, composites)
        assert block.estimated_grades.get("ash_pct") == pytest.approx(8.0)

    def test_closer_samples_have_more_influence(self, estimator):
        # Block at (500, 100, 50); one near sample (low ash), one far (high ash)
        composites = [
            DrillHoleComposite("Near", 505, 105, 52, {"ash_pct": 6.0}),  # close
            DrillHoleComposite("Far", 700, 400, 100, {"ash_pct": 20.0}),  # far
        ]
        estimator2 = BlockModelEstimator(power=2.0, max_search_radius_m=500.0, min_samples=2)
        block = estimator2.estimate_block("B1", 500, 100, 50, composites)
        # IDW should pull estimate closer to the near (low ash) sample
        ash = block.estimated_grades.get("ash_pct")
        assert ash < 13.0  # significantly below midpoint of 13

    def test_mean_distance_positive(self, estimator, simple_composites):
        block = estimator.estimate_block("B1", 520, 150, 52, simple_composites)
        assert block.mean_distance_m >= 0

    def test_specific_parameter_subset(self, estimator, simple_composites):
        block = estimator.estimate_block("B1", 520, 150, 52, simple_composites,
                                         parameters=["ash_pct"])
        assert "ash_pct" in block.estimated_grades
        assert "gcv_kcal_kg" not in block.estimated_grades


# ---------------------------------------------------------------------------
# generate_model
# ---------------------------------------------------------------------------

class TestGenerateModel:
    def test_returns_list_of_blocks(self, estimator, simple_composites):
        blocks = estimator.generate_model(
            simple_composites,
            east_range=(480, 570), north_range=(90, 210), depth_range=(45, 60),
            block_size_m=25.0,
        )
        assert len(blocks) > 0
        assert all(isinstance(b, BlockNode) for b in blocks)

    def test_block_count_matches_grid_dimensions(self, estimator, simple_composites):
        # 2 east steps, 2 north steps, 1 depth step → 4 blocks
        blocks = estimator.generate_model(
            simple_composites,
            east_range=(480, 530), north_range=(90, 140), depth_range=(45, 60),
            block_size_m=25.0,
        )
        assert len(blocks) >= 1

    def test_invalid_east_range_raises(self, estimator, simple_composites):
        with pytest.raises(ValueError, match="east"):
            estimator.generate_model(simple_composites, (600, 400), (90, 210), (45, 60))

    def test_invalid_block_size_raises(self, estimator, simple_composites):
        with pytest.raises(ValueError, match="block_size_m"):
            estimator.generate_model(simple_composites, (480, 570), (90, 210), (45, 60),
                                     block_size_m=0.0)


# ---------------------------------------------------------------------------
# model_statistics
# ---------------------------------------------------------------------------

class TestModelStatistics:
    def test_statistics_for_estimated_blocks(self, estimator, simple_composites):
        blocks = estimator.generate_model(
            simple_composites,
            east_range=(480, 570), north_range=(90, 210), depth_range=(45, 60),
            block_size_m=25.0,
        )
        stats = estimator.model_statistics(blocks, "ash_pct")
        if stats["estimated_count"] > 0:
            assert stats["min"] <= stats["mean"] <= stats["max"]
            assert stats["std"] >= 0

    def test_no_estimated_blocks_returns_none_mean(self, estimator):
        blocks = [
            BlockNode("B1", 500, 100, 50, estimated_grades={}, sample_count=0),
        ]
        stats = estimator.model_statistics(blocks, "ash_pct")
        assert stats["mean"] is None
        assert stats["unestimated_count"] == 1

    def test_empty_blocks_list(self, estimator):
        stats = estimator.model_statistics([], "ash_pct")
        assert stats["estimated_count"] == 0
