# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [1.3.0] - 2026-03-05
### Added
- `grade_tonnage_curve()`: generates grade-tonnage curve across cutoff grades with contained metal estimate
- `borehole_summary()`: per-hole statistics including total depth, max grade, and weighted-average grade
- 8 new unit tests covering grade-tonnage curve and borehole summary
### Improved
- README updated with grade-tonnage curve example and resource estimation workflow

## [1.2.0] - 2026-03-04
### Added
- `composite_intervals()`: length-weighted grade compositing to fixed interval length
- `estimate_resources()`: block model-based tonnage/grade/metal quantity estimation
- Grade cutoff filtering and percentile grade distribution reporting
- Auto-detection of grade columns if standard name not found
- Realistic sample data: 4 boreholes with 19 assay intervals
- 14 unit tests covering validation, compositing, and resource estimation
### Fixed
- `validate()` now checks from_m < to_m consistency (catches overlapping intervals)
- `preprocess()` auto-calculates interval_m from from_m/to_m if missing
## [1.1.0] - 2026-03-02
### Added
- Add 3D visualization and geostatistical kriging methods
- Improved unit test coverage
- Enhanced documentation with realistic examples
