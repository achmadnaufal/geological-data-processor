# Changelog

## [1.7.0] - 2026-03-26

### Added
- **VariogramModelFitter** (`src/variogram_model_fitter.py`) — geostatistical variogram model fitting for kriging
  - Three theoretical model types: Spherical, Exponential, Gaussian (+ Nugget-Only)
  - `VariogramModel` dataclass: nugget, partial sill, range, anisotropy ratio/azimuth
  - `gamma_at(h)`: theoretical semi-variance at any lag distance
  - Nugget effect classification: very_low / low / moderate / high / very_high
  - `fit()`: RMSE and R² assessment against experimental variogram points
  - Fit quality: GOOD / ACCEPTABLE / POOR classification
  - Reliable lag filtering: excludes lag classes with insufficient sample pairs
  - `select_best_model()`: automated model selection by RMSE from candidate list
  - `drill_spacing_recommendation()`: JORC Measured/Indicated/Inferred spacing from range
  - Kriging recommendations: high nugget effect warnings, range coverage checks, pair count alerts
- Unit tests: 15 new tests in `tests/test_variogram_model_fitter.py`

## [1.6.0] - 2026-03-23

### Added
- `src/composite_interval_sampler.py` — Borehole assay compositing for resource estimation
  - `AssayInterval` dataclass with full depth/grade validation
  - `CompositeIntervalSampler` with three compositing strategies:
    - `fixed_length_composite()` — regular downhole composites with Tromp-style overlap
    - `bench_composite()` — open-pit bench height composites
    - `seam_composite()` — zone/seam weighted-average composites
  - `hole_summary()` — per-borehole grade statistics and zone list
  - Missing-value handling (NaN/negative grades excluded from weighted averages)
- `data/sample_assay_intervals.csv` — 24 intervals across 3 Kalimantan coal boreholes
- 27 unit tests in `tests/test_composite_interval_sampler.py`

### References
- Rossi & Deutsch (2014) Mineral Resource Estimation, ch.5
- JORC Code 2012 Section 1

## [1.5.0] - 2026-03-22

### Added
- **Block Model Estimator** (`src/block_model_estimator.py`) — IDW grade interpolation for coal deposit block models
  - `DrillHoleComposite` dataclass for structured drill hole sample input (easting, northing, depth, grade dict)
  - `BlockNode` dataclass for estimated block output with grade values, sample count, mean distance
  - `estimate_block()` — IDW estimation at a single block centroid with configurable power, search radius, and min/max samples
  - `generate_model()` — sweeps a 3D grid to produce a full block model over a defined domain extent
  - `model_statistics()` — mean, min, max, std for any quality parameter across all estimated blocks
  - Handles coincident sample case (distance = 0) with exact-value assignment
  - Block IDs auto-generated as `E{e}_N{n}_D{d}` format aligned with common mine software conventions
  - Anisotropic extension: 3D Euclidean distance used; depth and horizontal treated equally (configurable via future extension)
  - Input validation on power, search radius, min/max samples, and grid range bounds
- **Unit tests** — 22 new tests in `tests/test_block_model_estimator.py` covering grid generation, IDW distance weighting, edge cases, and statistics

### References
- JORC Code 2012 — Australasian Code for Reporting of Mineral Resources
- Isaaks & Srivastava (1989) Applied Geostatistics, Oxford University Press
- Sinclair & Blackwell (2002) Applied Mineral Inventory Estimation

## [1.4.0] - 2026-03-21

### Added
- **Grade Outlier Detector** (`src/grade_outlier_detector.py`) — Competent Person QA/QC for assay data
  - Three detection methods: IQR fence, Modified Z-score (Iglewicz & Hoaglin), and log-normal probability limits
  - Flags high-grade (contamination, nugget) and low-grade (lost circulation, dilution) intervals
  - `top_outliers()` returns ranked outlier list for targeted re-assay decisions
  - Descriptive statistics (mean, median, p90, p95, p99) in every report
  - Auto-generated CP review recommendations including top-cut guidance
  - `GradeOutlierReport` and `OutlierFlag` dataclasses for structured pipeline integration
- **Sample data** — `data/assay_with_outliers.csv` with 3 drill holes and 2 planted outlier intervals
- **Unit tests** — 20 new tests in `tests/test_grade_outlier_detector.py` covering all 3 methods and edge cases

### References
- Iglewicz & Hoaglin (1993) How to Detect and Handle Outliers
- Sinclair & Blackwell (2002) Applied Mineral Inventory Estimation

## [1.3.0] - 2026-03-18

### Added
- **Drill Hole Validator** (`src/drill_hole_validator.py`) — JORC-aligned QA/QC for collar and assay data
  - `CollarRecord` dataclass with dip/azimuth/hole-type validation
  - `AssayInterval` dataclass with from/to depth and grade validation
  - `ValidationIssue` with ERROR/WARNING/INFO severity classification
  - `validate_collars()`: duplicate IDs, boundary check, default survey flags, shallow holes
  - `validate_assays()`: depth-exceeded, interval overlap, grade outlier, long interval, missing collar
  - `validate_all()`: combined run with severity-sorted output
  - `summary()`: structured QA/QC summary with JORC compliance boolean
  - Project boundary constraint for collar coordinate checks
- **Sample data** — `sample_data/drill_hole_collars.csv` with 10 realistic drill holes (Western Kalimantan project)
- **Unit tests** — 30 tests in `tests/test_drill_hole_validator.py` covering all validation rules and edge cases

### References
- JORC Code 2012, Table 1 — Sampling Techniques and Data
- AusIMM (2019) Mineral Resource estimation QA/QC guidelines

## [1.2.0] - 2026-03-15

### Added
- **JORC Resource Classification** — `classify_resource_confidence()`: Classifies resources as Measured/Indicated/Inferred per JORC 2012 based on drill spacing and sample density
- **Tonnage Estimator** — `estimate_tonnage()`: Calculates in-situ and contained tonnage from area, thickness, and bulk density inputs
- **Unit Tests** — 11 new tests in `tests/test_resource_classification.py` covering JORC classification, tonnage calculation, and error handling
- **README** — Added JORC classification and tonnage estimation usage examples

### Improved
- Docstrings across all methods now include `Raises` and `Example` sections

## [CURRENT] - 2026-03-07

### Added
- Add GIS raster data validation functions
- Enhanced README with getting started guide
- Comprehensive unit tests for core functions
- Real-world sample data and fixtures

### Improved
- Edge case handling for null/empty inputs
- Boundary condition validation

### Fixed
- Various edge cases and corner scenarios

---

## [2026-03-08]
- Enhanced documentation and examples
- Added unit test fixtures and test coverage
- Added comprehensive docstrings to key functions
- Added error handling for edge cases
- Improved README with setup and usage examples
