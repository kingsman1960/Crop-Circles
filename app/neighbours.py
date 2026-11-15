"""The parcels around a demo block for one plan year: what they grow, and which are (likely) planthopper nurseries.

A nursery for the plan year Y is winter wheat in Y on sugar beet of Y-1. So:
- Y = the year after the last observed season (e.g. 2026 after 2025): last season's beet fields are *likely* nurseries
  (the region's share of beet followed by wheat), drawn dashed in the planthopper colour; fills show last season's crops.
- later years: the neighbours' crops are not known, so they are grey.
- other farmers' saved plans (plans_store) for Y replace that: real outlines, their planned crops, confirmed nurseries.
Outlines exist only for demo blocks and saved plans; other parcels are circles of their area at their centre.
"""
from __future__ import annotations

import html

import numpy as np
import streamlit as st

from data import CROPS, GREY_LIGHT, crop_group, crop_names, landscape, parcel_geo, rgb
from i18n import num, pct

SHOW_FACTOR = 2   # show parcels up to this many flight ranges from the block centre
MAX_SHOWN = 2500
BEET_CODE = 1402

TEXT = {
    "en": {"neighbour": "Neighbouring parcel", "last": "{year}: {crop}", "unknown": "{year}: crops not known yet",
           "likely": "Likely nursery in {year}: sugar beet here in {prev}, and {btw} of such fields grow winter wheat next",
           "pull": "Up to {share} of the expected planthopper pressure on your block", "away": "{km} km from your block",
           "ring": "Planthopper flight range: {km} km", "shared": "Shared plan of another farmer", "planned": "{year}: {crop}",
           "nursery": "Nursery: winter wheat on {prev} sugar beet", "beet": "Sugar beet in {year}: receives planthopper pressure"},
    "de": {"neighbour": "Nachbarschlag", "last": "{year}: {crop}", "unknown": "{year}: Kulturen noch nicht bekannt",
           "likely": "Wahrscheinliche Kinderstube {year}: hier Zuckerrüben {prev}, und {btw} solcher Schläge tragen danach Winterweizen",
           "pull": "Bis zu {share} des erwarteten Zikadendrucks auf Ihren Block", "away": "{km} km von Ihrem Block",
           "ring": "Flugweite der Zikade: {km} km", "shared": "Geteilter Plan eines anderen Betriebs", "planned": "{year}: {crop}",
           "nursery": "Kinderstube: Winterweizen auf Zuckerrüben von {prev}", "beet": "Zuckerrüben {year}: bekommen Zikadendruck"},
}


def _circle(lon, lat, radius_m, n=14):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    dlat = radius_m / 111_320
    dlon = radius_m / (111_320 * np.cos(np.radians(lat)))
    ring = [[round(float(lon + dlon * np.cos(t)), 5), round(float(lat + dlat * np.sin(t)), 5)] for t in a]
    return {"type": "Polygon", "coordinates": [ring + ring[:1]]}


@st.cache_resource
def _outlines():
    """Parcel id -> FIONA outline (pipeline/landscape_geo.py), parsed once per process; parcels it lacks get a circle."""
    g = parcel_geo()
    return dict(zip(g["ids"], g["geoms"]))


def _btw(season):
    s = {x["season"]: x for x in landscape()[2]["seasons"]}
    return float(s.get(season, s[max(s)])["beet_to_wheat"])


@st.cache_data(show_spinner=False)
def neighbour_context(fid: str, season: int, r: int, lang: str = "en", plan_year: int | None = None) -> dict:
    """{"features": neighbouring parcels (FIONA outlines) and the flight ring for the planner map, "summary": likely
    nurseries near the block} for one plan year."""
    tx, plan_year = TEXT[lang], plan_year or season + 1
    par = landscape()[0]
    own = par[par.field == fid]
    fx, fy = own[["x", "y"]].mean()
    clon, clat = own[["lon", "lat"]].mean()
    dist = np.hypot(par.x - fx, par.y - fy)
    near = par[(dist <= SHOW_FACTOR * r) & (par.field != fid)].assign(dist=dist).nsmallest(MAX_SHOWN, "dist")
    names, de = crop_names(lang), crop_names("de")
    col, btw = f"c{season}", _btw(season)
    next_year = plan_year == season + 1  # last season's beet decides this year's nurseries
    likely = (near[col] == BEET_CODE) if (next_year and col in near) else near.dist < -1
    pull = near.area_ha * btw * np.exp(-near.dist / r) * likely
    total_pull = float(pull.sum()) or 1e-9

    feats = []
    for (pid, row), is_likely, pl in zip(near.iterrows(), likely, pull):
        props = {"kind": "context", "id": str(pid), "dist_m": round(float(row.dist)), "ha": round(float(row.area_ha), 2)}
        if next_year:
            code = int(row[col]) if col in row and row[col] == row[col] else -1
            props["rgb"] = rgb(CROPS[crop_group(de.get(code, ""))])[:3]
            lines = [f"<b>{tx['neighbour']}</b> · {num(row.area_ha, 1)} ha",
                     tx["last"].format(year=season, crop=html.escape(names.get(code, "–")))]
        else:
            props["rgb"] = rgb(GREY_LIGHT)[:3]
            lines = [f"<b>{tx['neighbour']}</b> · {num(row.area_ha, 1)} ha", tx["unknown"].format(year=plan_year)]
        if is_likely:
            props |= {"role": "likely", "nursery_ha": round(float(row.area_ha * btw), 2), "pull": round(float(pl), 4)}
            lines += [tx["likely"].format(year=plan_year, prev=season, btw=pct(btw)),
                      tx["pull"].format(share=pct(pl / total_pull))]
        lines.append(f"<span style='opacity:.7'>{tx['away'].format(km=num(row.dist / 1000, 1))}</span>")
        props["tip"] = "<br>".join(lines)
        geom = _outlines().get(int(pid)) or _circle(row.lon, row.lat, max(float(np.sqrt(row.area_ha * 1e4 / np.pi)), 20))
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    feats.append({"type": "Feature", "geometry": _circle(clon, clat, r, n=96),
                  "properties": {"kind": "ring", "id": "ring", "tip": tx["ring"].format(km=num(r / 1000, 1))}})
    within = likely & (near.dist <= r)
    return {"features": feats, "summary": {"likely_n": int(within.sum()), "likely_ha": float((near.area_ha * within).sum()),
                                           "btw": btw, "season": season, "plan_year": plan_year, "r": r}}


def collab_features(rows, plan_year, season, lang="en"):
    """Other farmers' saved plots for the plan year, with their crops; nurseries where their previous year (or the last
    observed season) had beet. Returns (features, outlines covering landscape parcels)."""
    import rotation
    from shapely.geometry import Point, shape
    tx = TEXT[lang]
    par = landscape()[0]
    prev = {(r_["user_id"], r_["field_id"], f["properties"]["id"]): f["properties"].get("plan")
            for r_ in rows if r_["year"] == plan_year - 1 for f in r_["plots"]}
    feats = []
    for r_ in (x for x in rows if x["year"] == plan_year):
        for f in r_["plots"]:
            crop = f["properties"].get("plan")
            g = shape(f["geometry"])
            key = (r_["user_id"], r_["field_id"], f["properties"]["id"])
            if key in prev:
                beet_before = prev[key] == "beet"
            elif plan_year - 1 == season:  # the parcel under the plot's centre, from the crop maps
                c = g.centroid
                d = np.hypot((par.lon - c.x) * 73_000, (par.lat - c.y) * 111_320)
                beet_before = bool(len(d) and d.min() < 150 and par[f"c{season}"].iloc[int(np.argmin(d.to_numpy()))] == BEET_CODE)
            else:
                beet_before = False
            role = "nursery" if crop in ("wheat", "barley") and beet_before else "beet" if crop == "beet" else ""
            colour = rotation.CROPS[crop]["rgb"] if crop in rotation.CROPS else rgb(GREY_LIGHT)[:3]
            lines = [f"<b>{tx['shared']}</b> · {num(float(f['properties'].get('ha') or 0), 1)} ha",
                     tx["planned"].format(year=plan_year, crop=html.escape(rotation.label(crop, lang)) if crop else "–")]
            if role == "nursery":
                lines.append(tx["nursery"].format(prev=plan_year - 1))
            elif role == "beet":
                lines.append(tx["beet"].format(year=plan_year))
            feats.append({"type": "Feature", "geometry": f["geometry"],
                          "properties": {"kind": "collab", "id": f"shared:{key[2]}:{len(feats)}", "rgb": colour,
                                         "role": role, "tip": "<br>".join(lines)}})
    return feats
