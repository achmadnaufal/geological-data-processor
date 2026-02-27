# Geological Data Processor

Borehole data processing, resource classification, and tonnage estimation for coal mining operations.

**Domain:** Coal Mining | **Standard:** JORC 2012

## Features

- **Borehole data processing** — load, validate, and preprocess assay data
- **High-grade interval identification** — flag intervals above grade threshold
- **Borehole summary statistics** — depth, interval count, weighted average grade
- **JORC 2012 Resource Classification** — Measured / Indicated / Inferred based on drill spacing
- **Tonnage Estimation** — in-situ and contained tonnage from area × thickness × density
- Supports CSV and Excel input formats

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from src.main import GeologicalDataProcessor

proc = GeologicalDataProcessor()
df = proc.load_data("data/boreholes.csv")
summary = proc.borehole_summary(df)
print(summary)
```

## Usage Examples

### JORC Resource Classification

```python
proc = GeologicalDataProcessor()
df = proc.load_data("data/assay_results.csv")

result = proc.classify_resource_confidence(df, drill_spacing_m=50.0)
print(f"Classification: {result['jorc_classification']}")      # Indicated
print(f"Confidence:     {result['confidence_score']:.1f}/100") # 68.3/100
print(f"Rationale:      {result['classification_rationale']}")
```

### Tonnage Estimation

```python
result = proc.estimate_tonnage(
    df,
    area_sqm=2_500_000,   # 250 ha orebody
    avg_thickness_m=4.5,
    bulk_density_t_m3=1.35,
    grade_column="grade",
)
print(f"In-situ:   {result['in_situ_tonnes']:,.0f} t")
print(f"Grade:     {result['avg_grade_pct']:.2f}%")
print(f"Contained: {result['contained_tonnes']:,.0f} t")
```

### Identify High-Grade Intervals

```python
high_grade = proc.identify_high_grade_intervals(df, grade_column="grade", threshold=76.0)
print(high_grade[["hole_id", "from_m", "to_m", "grade"]])
```

## Data Format

Expected CSV columns: `hole_id, from_m, to_m, interval_m, grade`

## Testing

```bash
pytest tests/ -v
```

## Project Structure

```
geological-data-processor/
├── src/
│   ├── main.py           # Core processing logic
│   └── data_generator.py # Sample data generator
├── tests/                # Unit tests
├── data/                 # Input data (gitignored)
├── examples/             # Usage scripts
└── sample_data/          # Sample datasets
```

## Edge Case Handling

This version includes improved validation and edge case handling across all data inputs.
See sample_data/realistic_data.csv for example datasets.

