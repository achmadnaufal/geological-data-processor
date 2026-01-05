"""
Geological borehole data processing, visualization, and resource estimation.

Provides tools for processing borehole collar/survey/assay data from mineral
exploration campaigns, computing composite intervals, and estimating in-situ
resource tonnage and grade using block model principles.

Author: github.com/achmadnaufal
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, List


class GeoDataProcessor:
    """
    Geological borehole data processor for mineral exploration.

    Handles collar/survey/assay data ingestion, interval compositing,
    grade distribution statistics, and block model-based resource estimation.

    Args:
        config: Optional dict with keys:
            - density_t_m3: Rock density for tonnage calculation (default 1.75)
            - cutoff_grade: Minimum grade cutoff for resource reporting (default 0)

    Example:
        >>> proc = GeoDataProcessor(config={"density_t_m3": 1.8, "cutoff_grade": 0.3})
        >>> df = proc.load_data("data/assay_data.csv")
        >>> resources = proc.estimate_resources(df)
        >>> print(resources)
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.density_t_m3 = self.config.get("density_t_m3", 1.75)
        self.cutoff_grade = self.config.get("cutoff_grade", 0)

    def load_data(self, filepath: str) -> pd.DataFrame:
        """
        Load geological data from CSV or Excel file.

        Args:
            filepath: Path to file. Expected columns for assay data:
                      hole_id, from_m, to_m, interval_m, grade_pct (or grade_gt for gold)

        Returns:
            DataFrame with borehole data.

        Raises:
            FileNotFoundError: If file does not exist.
        """
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Data file not found: {filepath}")
        if p.suffix in (".xlsx", ".xls"):
            return pd.read_excel(filepath)
        return pd.read_csv(filepath)

    def validate(self, df: pd.DataFrame) -> bool:
        """
        Validate borehole data for completeness and logical consistency.

        Args:
            df: DataFrame with borehole assay data.

        Returns:
            True if validation passes.

        Raises:
            ValueError: If empty, missing columns, or from >= to intervals.
        """
        if df.empty:
            raise ValueError("Input DataFrame is empty")
        df_cols = [c.lower().strip().replace(" ", "_") for c in df.columns]
        if "from_m" in df_cols and "to_m" in df_cols:
            df2 = df.copy()
            df2.columns = df_cols
            bad = df2[df2["from_m"] >= df2["to_m"]]
            if not bad.empty:
                raise ValueError(
                    f"{len(bad)} intervals have from_m >= to_m (overlapping or zero-length)"
                )
        return True

    def preprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and standardize borehole data.

        Normalizes column names, drops fully empty rows, calculates interval
        length if from_m and to_m are present.

        Args:
            df: Raw borehole DataFrame.

        Returns:
            Preprocessed DataFrame.
        """
        df = df.copy()
        df.dropna(how="all", inplace=True)
        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
        if "from_m" in df.columns and "to_m" in df.columns:
            df["interval_m"] = (df["to_m"] - df["from_m"]).round(3)
        num_cols = df.select_dtypes(include="number").columns
        for col in num_cols:
            if df[col].isnull().any():
                df[col].fillna(df[col].median(), inplace=True)
        return df

    def composite_intervals(
        self, df: pd.DataFrame, composite_length_m: float = 1.0, grade_col: str = "grade_pct"
    ) -> pd.DataFrame:
        """
        Composite borehole assay intervals to a fixed length.

        Compositing reduces the effect of variable-length sample intervals
        by recalculating length-weighted average grades over fixed intervals.

        Args:
            df: Preprocessed borehole assay DataFrame with interval_m and grade_col.
            composite_length_m: Target composite interval length in metres.
            grade_col: Name of the grade column to composite.

        Returns:
            DataFrame of composited intervals per hole_id.
        """
        df = self.preprocess(df)
        if "interval_m" not in df.columns or grade_col not in df.columns:
            raise ValueError(f"Columns 'interval_m' and '{grade_col}' required for compositing")

        results = []
        hole_col = "hole_id" if "hole_id" in df.columns else df.columns[0]

        for hole, grp in df.groupby(hole_col):
            grp = grp.sort_values("from_m") if "from_m" in grp.columns else grp
            intervals = grp["interval_m"].values
            grades = grp[grade_col].values
            total_length = intervals.sum()
            n_composites = max(1, int(np.round(total_length / composite_length_m)))
            comp_length = total_length / n_composites

            # Length-weighted grade for each composite block
            cumulative = np.concatenate([[0], np.cumsum(intervals)])
            comp_grades = []
            for i in range(n_composites):
                comp_start = i * comp_length
                comp_end = (i + 1) * comp_length
                weighted_sum = 0
                weight_total = 0
                for j, (s, e) in enumerate(zip(cumulative[:-1], cumulative[1:])):
                    overlap = max(0, min(e, comp_end) - max(s, comp_start))
                    if overlap > 0:
                        weighted_sum += grades[j] * overlap
                        weight_total += overlap
                comp_grades.append(weighted_sum / weight_total if weight_total > 0 else 0)

            for i, g in enumerate(comp_grades):
                results.append({
                    hole_col: hole,
                    "composite_from_m": round(i * comp_length, 2),
                    "composite_to_m": round((i + 1) * comp_length, 2),
                    "composite_length_m": round(comp_length, 3),
                    f"composite_{grade_col}": round(g, 4),
                })

        return pd.DataFrame(results)

    def estimate_resources(
        self,
        df: pd.DataFrame,
        grade_col: str = "grade_pct",
        cutoff_grade: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Estimate in-situ mineral resources from borehole assay data.

        Uses a simplified block model approach: each sample interval is treated
        as a representative volume, tonnage is calculated from interval volume
        and rock density, and metal quantity is derived from grade × tonnage.

        Args:
            df: Borehole assay DataFrame (preprocessed).
            grade_col: Column name for grade values.
            cutoff_grade: Minimum grade to include in resource estimate.
                          Overrides config cutoff_grade if provided.

        Returns:
            Dict with:
                - total_tonnes: In-situ resource tonnage
                - mean_grade: Average grade above cutoff
                - metal_quantity: Total metal in grade units × tonnes
                - above_cutoff_intervals: Number of intervals above cutoff
                - grade_distribution: Percentile breakdown of grades
                - cutoff_grade_used: The cutoff grade applied
        """
        df = self.preprocess(df)
        cutoff = cutoff_grade if cutoff_grade is not None else self.cutoff_grade

        if grade_col not in df.columns:
            # Try to find a grade column automatically
            candidate = [c for c in df.columns if "grade" in c.lower()]
            if candidate:
                grade_col = candidate[0]
            else:
                raise ValueError(f"Grade column '{grade_col}' not found. Available: {list(df.columns)}")

        if "interval_m" not in df.columns:
            df["interval_m"] = 1.0  # assume 1m intervals if not specified

        # Apply cutoff
        above = df[df[grade_col] >= cutoff].copy()

        # Tonnage: assume 1m² cross-section per sample interval (simplified)
        above["tonnes"] = above["interval_m"] * 1.0 * self.density_t_m3 * 1000  # per 1m² block in kt
        total_tonnes = above["tonnes"].sum()
        mean_grade = float(np.average(above[grade_col], weights=above["interval_m"])) if not above.empty else 0.0
        metal_quantity = total_tonnes * mean_grade / 100 if not above.empty else 0.0

        grade_dist = {}
        if not above.empty:
            for p in [10, 25, 50, 75, 90]:
                grade_dist[f"p{p}"] = round(float(np.percentile(above[grade_col], p)), 4)

        return {
            "cutoff_grade_used": cutoff,
            "above_cutoff_intervals": int(len(above)),
            "total_tonnes": round(total_tonnes, 1),
            "mean_grade": round(mean_grade, 4),
            "metal_quantity": round(metal_quantity, 2),
            "grade_distribution": grade_dist,
            "grade_col_used": grade_col,
        }

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run descriptive analysis and return summary metrics."""
        df = self.preprocess(df)
        result = {
            "total_records": len(df),
            "columns": list(df.columns),
            "missing_pct": (df.isnull().sum() / len(df) * 100).round(1).to_dict(),
        }
        numeric_df = df.select_dtypes(include="number")
        if not numeric_df.empty:
            result["summary_stats"] = numeric_df.describe().round(3).to_dict()
            result["totals"] = numeric_df.sum().round(2).to_dict()
            result["means"] = numeric_df.mean().round(3).to_dict()
        return result

    def run(self, filepath: str) -> Dict[str, Any]:
        """Full pipeline: load → validate → analyze."""
        df = self.load_data(filepath)
        self.validate(df)
        return self.analyze(df)

    def to_dataframe(self, result: Dict) -> pd.DataFrame:
        """Convert result dict to flat DataFrame for export."""
        rows = []
        for k, v in result.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    rows.append({"metric": f"{k}.{kk}", "value": vv})
            else:
                rows.append({"metric": k, "value": v})
        return pd.DataFrame(rows)


    def grade_tonnage_curve(
        self,
        df: pd.DataFrame,
        grade_col: str = "grade_pct",
        cutoffs: Optional[List[float]] = None,
    ) -> pd.DataFrame:
        """
        Generate a grade-tonnage curve for resource estimation.

        For each cutoff grade, calculates the tonnage above cutoff,
        average grade above cutoff, and contained metal/mineral.

        Args:
            df: Assay DataFrame with interval_m and grade column.
            grade_col: Name of grade column (e.g. 'grade_pct', 'grade_gt').
            cutoffs: List of cutoff grade values. Defaults to 0.0 to max in 10 steps.

        Returns:
            DataFrame with cutoff_grade, tonnes_above_cutoff, avg_grade_above_cutoff,
            contained_metal (tonnes * avg_grade).
        """
        df = self.preprocess(df)
        if grade_col not in df.columns:
            available = [c for c in df.columns if "grade" in c.lower()]
            raise ValueError(f"Grade column '{grade_col}' not found. Available: {available}")
        if "interval_m" not in df.columns:
            raise ValueError("Column 'interval_m' required for grade-tonnage curve")

        max_grade = float(df[grade_col].max())
        if cutoffs is None:
            cutoffs = list(np.linspace(0, max_grade * 0.9, 10).round(4))

        density = self.density_t_m3
        rows = []
        for cutoff in sorted(cutoffs):
            above = df[df[grade_col] >= cutoff]
            if above.empty:
                rows.append({
                    "cutoff_grade": cutoff,
                    "tonnes_above_cutoff": 0.0,
                    "avg_grade_above_cutoff": None,
                    "contained_metal": 0.0,
                    "interval_count": 0,
                })
                continue
            # Approximate tonnage: interval length × assumed cross-section × density
            # Using 1 m² cross-section per borehole interval (relative comparison)
            tonnage = float((above["interval_m"] * density).sum())
            avg_grade = float(
                np.average(above[grade_col], weights=above["interval_m"])
            )
            rows.append({
                "cutoff_grade": round(cutoff, 4),
                "tonnes_above_cutoff": round(tonnage, 1),
                "avg_grade_above_cutoff": round(avg_grade, 4),
                "contained_metal": round(tonnage * avg_grade / 100, 2),
                "interval_count": len(above),
            })
        return pd.DataFrame(rows)

    def borehole_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Summarize borehole statistics per hole_id.

        Args:
            df: Assay DataFrame with hole_id, interval_m, and grade columns.

        Returns:
            DataFrame with hole_id, total_depth_m, interval_count,
            max_grade, avg_grade, and weighted_avg_grade.
        """
        df = self.preprocess(df)
        grade_cols = [c for c in df.columns if "grade" in c.lower()]
        if "hole_id" not in df.columns:
            raise ValueError("Column 'hole_id' required for borehole summary")

        agg = df.groupby("hole_id").agg(
            total_depth_m=("interval_m", "sum") if "interval_m" in df.columns else ("hole_id", "count"),
            interval_count=("hole_id", "count"),
        ).reset_index()

        if grade_cols:
            g = grade_cols[0]
            grade_agg = df.groupby("hole_id").apply(
                lambda x: pd.Series({
                    "max_grade": x[g].max(),
                    "avg_grade": x[g].mean(),
                    "weighted_avg_grade": (
                        np.average(x[g], weights=x["interval_m"])
                        if "interval_m" in x.columns else x[g].mean()
                    ),
                })
            ).reset_index()
            agg = agg.merge(grade_agg, on="hole_id")

        return agg.round(4)

    def classify_resource_confidence(
        self,
        df: pd.DataFrame,
        drill_spacing_m: float,
        min_samples: int = 3,
    ) -> dict:
        """
        Classify mineral resource confidence per JORC 2012 framework.

        Assigns Measured / Indicated / Inferred confidence based on
        drill spacing and data density.

        Args:
            df: DataFrame with hole_id and assay data
            drill_spacing_m: Average drill hole spacing in metres
            min_samples: Minimum number of samples for classification

        Returns:
            Dict with jorc_classification, confidence_score (0-100),
            drill_spacing_m, sample_count, and classification_rationale

        Raises:
            ValueError: If drill_spacing_m <= 0 or DataFrame is empty

        Example:
            >>> proc = GeologicalDataProcessor()
            >>> result = proc.classify_resource_confidence(df, drill_spacing_m=50.0)
            >>> print(result["jorc_classification"])  # "Indicated"
        """
        if drill_spacing_m <= 0:
            raise ValueError("drill_spacing_m must be positive")
        if df is None or len(df) == 0:
            raise ValueError("DataFrame cannot be empty")

        sample_count = len(df)
        unique_holes = df["hole_id"].nunique() if "hole_id" in df.columns else 1

        # JORC 2012 classification by drill spacing
        if drill_spacing_m <= 25 and sample_count >= min_samples * 3 and unique_holes >= 4:
            classification = "Measured"
            confidence_score = min(100.0, 95 - (drill_spacing_m / 25) * 20)
            rationale = "Tight drill spacing with high sample density — high geological confidence"
        elif drill_spacing_m <= 100 and sample_count >= min_samples and unique_holes >= 2:
            classification = "Indicated"
            confidence_score = min(80.0, 75 - (drill_spacing_m - 25) / 75 * 30)
            rationale = "Moderate drill spacing — sufficient for Indicated resource estimation"
        else:
            classification = "Inferred"
            confidence_score = max(10.0, 40 - (drill_spacing_m - 100) / 100 * 20)
            rationale = "Wide drill spacing or limited data — inferred classification only"

        # Adjust confidence for sample count
        if sample_count < min_samples:
            confidence_score *= 0.5
            classification = "Inferred"
            rationale = f"Insufficient samples (need ≥ {min_samples})"

        return {
            "jorc_classification": classification,
            "confidence_score": round(confidence_score, 1),
            "drill_spacing_m": drill_spacing_m,
            "sample_count": sample_count,
            "unique_drill_holes": unique_holes,
            "classification_rationale": rationale,
            "reporting_standard": "JORC 2012",
        }

    def estimate_tonnage(
        self,
        df: pd.DataFrame,
        area_sqm: float,
        avg_thickness_m: float,
        bulk_density_t_m3: float = 1.35,
        grade_column: str = "grade",
    ) -> dict:
        """
        Estimate resource tonnage and contained metal/mineral.

        Args:
            df: Assay DataFrame
            area_sqm: Ore body area in square metres
            avg_thickness_m: Average ore thickness in metres
            bulk_density_t_m3: In-situ bulk density (t/m³), default 1.35 for coal
            grade_column: Name of grade column to use

        Returns:
            Dict with in_situ_tonnes, contained_tonnes, avg_grade, volume_m3

        Raises:
            ValueError: If area, thickness, or density are non-positive

        Example:
            >>> result = proc.estimate_tonnage(df, area_sqm=500000, avg_thickness_m=4.5)
            >>> print(f"In-situ: {result['in_situ_tonnes']:,.0f} t")
        """
        if area_sqm <= 0:
            raise ValueError("area_sqm must be positive")
        if avg_thickness_m <= 0:
            raise ValueError("avg_thickness_m must be positive")
        if bulk_density_t_m3 <= 0:
            raise ValueError("bulk_density_t_m3 must be positive")

        volume_m3 = area_sqm * avg_thickness_m
        in_situ_tonnes = volume_m3 * bulk_density_t_m3

        avg_grade = None
        contained_tonnes = None
        if df is not None and grade_column in df.columns:
            numeric_grades = pd.to_numeric(df[grade_column], errors="coerce").dropna()
            if len(numeric_grades) > 0:
                avg_grade = float(numeric_grades.mean())
                contained_tonnes = in_situ_tonnes * avg_grade / 100.0

        return {
            "in_situ_tonnes": round(in_situ_tonnes, 0),
            "volume_m3": round(volume_m3, 0),
            "bulk_density_t_m3": bulk_density_t_m3,
            "avg_grade_pct": round(avg_grade, 3) if avg_grade is not None else None,
            "contained_tonnes": round(contained_tonnes, 0) if contained_tonnes is not None else None,
            "area_sqm": area_sqm,
            "avg_thickness_m": avg_thickness_m,
        }
