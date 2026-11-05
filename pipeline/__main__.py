"""Run the whole pipeline: python -m pipeline (from the repo root)."""
from pipeline import climate, geo, hls, landscape, phenology, strategies

for step in (geo, phenology, climate, strategies, landscape, hls):
    print(f"[{step.__name__}]")
    step.main()
