# Changelog

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
