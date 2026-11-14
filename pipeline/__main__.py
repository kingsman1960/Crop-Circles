"""Run the whole pipeline: python -m pipeline (from the repo root)."""
from pipeline import climate, geo, hls, landscape, phenology, planthopper_edge_effect, strategies

for step in (geo, phenology, climate, strategies, landscape, hls, planthopper_edge_effect):
    print(f"[{step.__name__}]")
    step.main()
