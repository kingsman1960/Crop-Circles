"""Run the whole pipeline: python -m pipeline (from the repo root)."""
from pipeline import climate, geo, hls, landscape, phenology, planthopper_edge_effect, planthopper_region, strategies

for step in (geo, phenology, climate, strategies, landscape, hls, planthopper_edge_effect, planthopper_region):
    print(f"[{step.__name__}]")
    step.main()
