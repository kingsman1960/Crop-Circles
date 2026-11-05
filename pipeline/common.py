"""Paths and helpers shared by the pipeline scripts (raw -> processed)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREP = ROOT / "crop-circles-data-prep" / "crop-circles-data-prep"
RAW = PREP / "data" / "raw"
PROC = PREP / "data" / "processed"
CONTENT = ROOT / "content"
CONFIG = json.loads((PREP / "config" / "study_area.json").read_text(encoding="utf-8"))
FIELDS = CONFIG["fields"]


def out(name):
    """Path inside data/processed/, parent folders created."""
    p = PROC / name
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def check(name, df, date_col=None):
    """Short check line every script prints for its output."""
    rng = f", {df[date_col].min()} -> {df[date_col].max()}" if date_col else ""
    print(f"  {name}: {len(df):,} rows{rng}, missing cells {int(df.isna().sum().sum()):,}")
