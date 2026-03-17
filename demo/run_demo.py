"""
Geological Data Processor — live demo
Run: python3 demo/run_demo.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.main import GeoDataProcessor

DATA = os.path.join(os.path.dirname(__file__), "../sample_data/borehole_assay.csv")

print("=" * 62)
print("  Geological Data Processor — Demo")
print("=" * 62)

proc = GeoDataProcessor(config={"density_t_m3": 1.75, "cutoff_grade": 0.3})
df = proc.load_data(DATA)
df_proc = proc.preprocess(df)
print(f"\n✓ Loaded {len(df)} borehole intervals from {os.path.basename(DATA)}")
print(f"  Drill holes : {df_proc['hole_id'].nunique()}")
print(f"  Grade range : {df_proc['grade_pct'].min():.2f}% – {df_proc['grade_pct'].max():.2f}%")
print(f"  Lithologies : {sorted(df_proc['lithology'].unique())}")

# Borehole summary
summary = proc.borehole_summary(df)
print(f"\n✓ Borehole Summary:")
print(f"  {'Hole ID':<10} {'Depth (m)':>10}  {'Intervals':>10}  {'Max Grade':>10}  {'Wtd Avg Grade':>14}")
print(f"  {'-'*58}")
for _, row in summary.iterrows():
    print(f"  {row['hole_id']:<10} {row['total_depth_m']:>10.1f}  {row['interval_count']:>10}  {row['max_grade']:>10.2f}%  {row['weighted_avg_grade']:>13.2f}%")

# Resource estimate (cutoff 0.3%)
resources = proc.estimate_resources(df, grade_col="grade_pct", cutoff_grade=0.3)
print(f"\n✓ Resource Estimate (cutoff grade: {resources['cutoff_grade_used']}%):")
print(f"  Intervals above cutoff : {resources['above_cutoff_intervals']}")
print(f"  In-situ tonnage        : {resources['total_tonnes']:,.0f} t")
print(f"  Weighted avg grade     : {resources['mean_grade']:.4f}%")
print(f"  Contained metal        : {resources['metal_quantity']:,.1f} t")
print(f"  Grade distribution     :")
for p, v in resources["grade_distribution"].items():
    print(f"    {p}: {v:.4f}%")

# Grade-tonnage curve
gtc = proc.grade_tonnage_curve(df, grade_col="grade_pct")
print(f"\n✓ Grade-Tonnage Curve (sensitivity to cutoff):")
print(f"  {'Cutoff %':>9}  {'Tonnes':>12}  {'Avg Grade %':>12}  {'Contained t':>12}")
print(f"  {'-'*50}")
for _, row in gtc.iterrows():
    if row['avg_grade_above_cutoff'] is not None:
        print(f"  {row['cutoff_grade']:>9.4f}  {row['tonnes_above_cutoff']:>12,.1f}  {row['avg_grade_above_cutoff']:>11.4f}%  {row['contained_metal']:>12,.2f}")

# JORC classification
jorc = proc.classify_resource_confidence(df_proc, drill_spacing_m=50.0)
print(f"\n✓ JORC 2012 Resource Classification (50m drill spacing):")
print(f"  Classification  : {jorc['jorc_classification'].upper()}")
print(f"  Confidence score: {jorc['confidence_score']}/100")
print(f"  Sample count    : {jorc['sample_count']}")
print(f"  Unique holes    : {jorc['unique_drill_holes']}")
print(f"  Rationale       : {jorc['classification_rationale']}")

# Tonnage estimate
tonnage = proc.estimate_tonnage(df_proc, area_sqm=250000, avg_thickness_m=4.5, grade_column="grade_pct")
print(f"\n✓ Tonnage Estimation (250,000 m² × 4.5 m seam):")
print(f"  Volume          : {tonnage['volume_m3']:,.0f} m³")
print(f"  In-situ tonnage : {tonnage['in_situ_tonnes']:,.0f} t")
print(f"  Avg grade       : {tonnage['avg_grade_pct']:.3f}%")
print(f"  Contained metal : {tonnage['contained_tonnes']:,.0f} t")

print("\n" + "=" * 62)
print("  ✅ Demo complete")
print("=" * 62)
