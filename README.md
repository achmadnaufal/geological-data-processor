# Geological Data Processor

Borehole data processing, interval compositing, and mineral resource estimation for mining exploration.

## Domain Context

In coal and mineral exploration, drill holes (boreholes) are sampled at regular intervals to
measure grade (e.g. coal quality, mineral concentration). This tool helps geologists process
raw assay data: standardize intervals, composite to fixed lengths, and estimate in-situ
resources (tonnage × grade) above a cutoff grade.

## Features
- **Borehole data ingestion**: CSV/Excel with automatic column normalization
- **Interval validation**: Catches overlapping or zero-length intervals
- **Compositing**: Length-weighted grade compositing to fixed interval lengths
- **Resource estimation**: Tonnage and metal quantity calculation with cutoff filtering
- **Grade distribution**: Percentile breakdown (P10/P25/P50/P75/P90)
- **Sample data**: Realistic multi-hole assay dataset

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from src.main import GeoDataProcessor

proc = GeoDataProcessor(config={"density_t_m3": 1.80, "cutoff_grade": 0.3})

df = proc.load_data("sample_data/borehole_assay.csv")
proc.validate(df)

# Estimate resources above 0.3% cutoff
resources = proc.estimate_resources(df, cutoff_grade=0.3)
print(f"Total Tonnes: {resources['total_tonnes']:,.1f}")
print(f"Mean Grade:   {resources['mean_grade']:.3f}%")
print(f"Metal Qty:    {resources['metal_quantity']:.2f}")

# Composite to 2m intervals
composites = proc.composite_intervals(df, composite_length_m=2.0)
print(composites.head())
```

## Data Format

| Column | Description |
|--------|-------------|
| hole_id | Borehole identifier |
| from_m | Start depth (m) |
| to_m | End depth (m) |
| grade_pct | Assay grade (%) |
| lithology | Rock type description |

## Running Tests

```bash
pytest tests/ -v
```

---

## [v1.3.0] Grade-Tonnage Curve & Borehole Summary

```python
# Generate grade-tonnage curve at multiple cutoffs
df["interval_m"] = df["to_m"] - df["from_m"]
gtc = proc.grade_tonnage_curve(df, cutoffs=[0.0, 0.3, 0.5, 1.0, 1.5])
print(gtc[["cutoff_grade", "tonnes_above_cutoff", "avg_grade_above_cutoff"]])
# cutoff_grade  tonnes_above_cutoff  avg_grade_above_cutoff
#          0.0               126.0                  0.7789
#          0.3               105.0                  0.9124
#          1.0                42.0                  1.6500

# Summarize per borehole
summary = proc.borehole_summary(df)
print(summary[["hole_id", "total_depth_m", "weighted_avg_grade"]])
```
