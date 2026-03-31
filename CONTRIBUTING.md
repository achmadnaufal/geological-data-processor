# Contributing to Geological Data Processor

Thank you for your interest in contributing!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/geological-data-processor.git`
3. Install dev dependencies: `pip install -r requirements.txt`
4. Create a feature branch: `git checkout -b feat/your-feature`

## Development Guidelines

- Follow PEP 8 style conventions
- Add type hints to all public functions
- Write unit tests for new features (`pytest tests/ -v`)
- Update `CHANGELOG.md` with a summary of changes

## Areas for Contribution

- Additional resource estimation methods (kriging, inverse distance weighting)
- Support for JORC 2012 Table 1 checklist generator
- Integration with Leapfrog / MICROMINE export formats
- 3D visualisation of drill holes and grade shells (matplotlib / plotly)
- Variogram modelling for geostatistical analysis

## Submitting a PR

1. Ensure all tests pass: `pytest tests/ -v`
2. Use semantic commit messages: `feat: add kriging interpolation for grade estimation`
3. Open a pull request with a clear description of the change

Questions? Open an issue.
