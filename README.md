# Geological Data Processor

Geological borehole data processing, visualization, and resource estimation utilities

## Features
- Data ingestion from CSV/Excel input files
- Automated analysis and KPI calculation
- Summary statistics and trend reporting
- Sample data generator for testing and development

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

```python
from src.main import GeoDataProcessor

analyzer = GeoDataProcessor()
df = analyzer.load_data("data/sample.csv")
result = analyzer.analyze(df)
print(result)
```

## Data Format

Expected CSV columns: `hole_id, from_m, to_m, lithology, coal_seam, calorific_value, thickness_m`

## Project Structure

```
geological-data-processor/
├── src/
│   ├── main.py          # Core analysis logic
│   └── data_generator.py # Sample data generator
├── data/                # Data directory (gitignored for real data)
├── examples/            # Usage examples
├── requirements.txt
└── README.md
```

## License

MIT License — free to use, modify, and distribute.

## 🚀 New Features (2026-03-02)
- Add 3D visualization and geostatistical kriging methods
- Enhanced error handling and edge case coverage
- Comprehensive unit tests and integration examples
