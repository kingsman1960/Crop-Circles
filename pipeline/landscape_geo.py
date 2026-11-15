"""Parcel outlines for the Our region map: one simplified FIONA polygon per landscape parcel.

Writes landscape_parcels{suffix}.geojson ({"ids": [...], "geoms": [...]} in EPSG:4326), simplified to ~8 m and
rounded to 5 decimals (~1 m), which is finer than every zoom the map offers. The app reads it with
data.parcel_geo() and paints the parcels as polygons. `python -m pipeline.landscape` writes the file from the
geometry it already holds, so export and parcel ids always match; the standalone run
(`python -m pipeline.landscape_geo`, `--bw` for all of Baden-Württemberg) regenerates it without re-running the
pipeline, pairing the parquet ids with the raw FIONA export and reporting how many parcels it found.
"""
import json
import re
import sys

import pandas as pd
import shapely

from pipeline import geo
from pipeline.common import RAW, out

TOL = 8.0  # metres of simplification
DP = 5     # decimals of EPSG:4326


def _round(c):
    """Recursively round coordinates: rings before polygons; geometry to DP decimals."""
    return [[round(x, DP), round(y, DP)] for x, y in c] if isinstance(c[0][0], (int, float)) else [_round(r) for r in c]


def write_parcels_geo(ids, geoms, sfx=""):
    """Simplify, reproject and store parcels (ids unique per FIONA object); ids/geom in EPSG:25832."""
    d = pd.DataFrame({"id": pd.Series(ids, dtype="int64").to_numpy(), "geom": list(geoms)}).drop_duplicates("id")
    outg = geo.reproj([g.simplify(TOL, preserve_topology=True) for g in d.geom], 25832, 4326)
    data = json.dumps({"ids": d.id.tolist(), "geoms": [{"type": g.geom_type, "coordinates": _round(g.__geo_interface__["coordinates"])}
                                                       for g in outg]}, separators=(",", ":"))
    out(f"landscape_parcels{sfx}.geojson").write_text(data, encoding="utf-8")
    print(f"  landscape_parcels{sfx}.geojson: {len(d):,} parcels, {len(data) / 1e6:.1f} MB")


def from_raw(tag="bbox"):
    """Parcels of landscape_parcels{suffix}.parquet found in the raw FIONA exports: preferred is the unsuffixed
    export (the one the parquet was built from), then the year-stamped ones. Returns (ids, geoms)."""
    sfx = "" if tag == "bbox" else f"_{tag}"
    wanted = set(pd.read_parquet(out(f"landscape_parcels{sfx}.parquet"), columns=["id"]).id.astype("int64"))
    groups = {}
    for f in RAW.glob(f"fiona/fiona_{tag}_*.json"):
        groups.setdefault(re.match(rf"fiona_{tag}(?:_(\d{{4}}))?_p\d+$", f.stem).group(1) or "", []).append(f)
    seen = {}
    for year in [""] + sorted(groups):  # unsuffixed first, then by increasing year
        for f in groups.get(year, []):
            for ft in json.loads(f.read_text(encoding="utf-8"))["features"]:
                oid = ft["properties"]["object_id"]
                if oid in wanted and oid not in seen:
                    seen[oid] = shapely.from_geojson(json.dumps(ft["geometry"]))
        if len(seen) == len(wanted):
            break
    print(f"  raw FIONA: {len(seen):,} of {len(wanted):,} parcels found for {tag}"
          + ("" if len(seen) == len(wanted) else " - run the export of the year the parquet was built from"))
    return sorted(seen), [seen[i] for i in sorted(seen)]


if __name__ == "__main__":
    tag = "bw" if "--bw" in sys.argv else "bbox"
    ids, geoms = from_raw(tag)
    if ids:
        write_parcels_geo(ids, geoms, "" if tag == "bbox" else f"_{tag}")
