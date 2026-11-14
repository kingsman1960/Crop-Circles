"""Plot editor: a map like the field maps where plots can be selected, merged and cut.

The browser side (frontend/index.html) only draws and collects clicks. Every geometry change happens here,
in metres (EPSG:25832, ETRS89 / UTM 32N), so areas are true and cut pieces always fit their block exactly.

    from plot_editor import plot_editor
    res = plot_editor(features, key=f"plots_{fid}_{yr}", outline=outline,
                      view={"lat": p["lat"], "lon": p["lon"], "zoom": 14.4})
    res["features"]   # the plots as they are now (GeoJSON features)

Each feature needs properties["id"] and properties["rgb"] ([r, g, b] or [r, g, b, a]).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from streamlit.errors import StreamlitAPIException
from pyproj import Transformer
from shapely.geometry import LineString, mapping, shape
from shapely.ops import split, transform, unary_union

_component = components.declare_component("plot_editor", path=str(Path(__file__).parent / "frontend"))
_TO_M = Transformer.from_crs(4326, 25832, always_xy=True).transform
_TO_DEG = Transformer.from_crs(25832, 4326, always_xy=True).transform
_SNAP_M = 0.05   # closes hairline gaps between plots when merging
_REACH_M = 10    # a cut line is stretched this far at both ends, so stopping just short of an edge still cuts

LABELS = {
    "select": "Select", "cut": "Cut", "merge": "Merge", "undo": "Undo", "finish": "Finish cut", "working": "Working…",
    "hint_select": "Click a plot to select it. Shift-click to add more.",
    "hint_cut": "Click to draw a line across the plots. Double-click or Enter to cut, Esc to cancel.",
    "err_adjacent": "Only plots that touch each other can be merged.",
    "err_cut": "The line has to cross a plot from one edge to the other.",
    "err_small": "That cut would leave a piece smaller than {ha} ha, so it was skipped.",
    # crop painting (only shown when a palette is given)
    "crop": "Crop…", "no_crop": "No crop (just look)", "clear": "Remove plan", "plan": "Plan", "not_planned": "Not planned yet",
    "hint_paint": "Red: breaks a rotation rule. Green: a good fit. Click a plot to plan this crop there, click again to undo.",
    "level_bad": "Breaks a rotation rule", "level_warn": "Possible, with a risk", "level_ok": "Fine",
    "level_good": "Good fit", "level_unknown": "No history",
}


def plot_editor(features: list[dict], *, key: str, outline: dict | None = None, view: dict | None = None,
                height: int = 430, labels: dict | None = None, tooltip: str | None = "{id} · {ha} ha",
                min_ha: float = 0.05, report_selection: bool = False, palette: list[dict] | None = None,
                annotate=None) -> dict:
    """Draw the editable plot map and return {"features": [...], "selected": [ids]}.

    key:              one key per block, e.g. f"plots_{fid}". The edits live under it in session state.
    outline:          optional GeoJSON FeatureCollection drawn as the dark block outline.
    view:             {"lat", "lon", "zoom"}; if left out the map fits the plots.
    labels:           any LABELS entries to replace, e.g. with t(...) for German.
    tooltip:          template filled from a plot's properties, e.g. "{group}: {crop}, {ha} ha". None turns it off.
                      A plot with properties["tip"] (HTML) shows that instead.
    min_ha:           cuts that would leave a smaller piece are refused.
    report_selection: send every selection change to Python (one rerun per click). Off by default to keep it snappy;
                      merge always sends the ids it needs.
    palette:          crops to plan with: [{"key", "label", "rgb", "family"}]. Adds the crop drop-down. A plot's
                      properties["fit"][crop_key] = {"level": "bad|warn|ok|good|unknown", "why": [...]} colours it
                      while that crop is picked, and painting stores the crop in properties["plan"].
    annotate:         function(features) run on every rerun, after the edits; it may add properties such as rgb,
                      tip and fit (e.g. from the history under each plot, which changes when plots are cut).
    Runs inside @st.fragment too, and then only reruns the fragment.
    """
    lab = LABELS | (labels or {})
    s = _state(key, features)
    if annotate:
        annotate(s["features"])
    event = _component(features=s["features"], selected=s["selected"], revision=s["revision"], outline=outline,
                       view=view, height=height, labels=lab, tooltip=tooltip, can_undo=bool(s["history"]),
                       message=s["message"], report_selection=report_selection, basemap=_basemap(),
                       palette=palette or [], key=key, default=None)
    if event and event.get("nonce") != s["nonce"]:
        s["nonce"] = event["nonce"]
        if _apply(s, event, lab, min_ha):
            _rerun()  # the map has to be drawn again with the new plots
    return {"features": s["features"], "selected": list(s["selected"])}


def metric(feature: dict):
    """A feature's geometry as a shapely shape in metres (EPSG:25832)."""
    return _metric(feature)


def _rerun():
    """Rerun only the fragment when we are in one, else the whole page."""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def update_plots(key: str, ids: list[str], **props) -> None:
    """Change properties of some plots from Python, e.g. update_plots(key, ids, crop="Maize", rgb=[...])."""
    s = st.session_state[_skey(key)]
    _remember(s)
    for f in s["features"]:
        if f["properties"]["id"] in ids:
            f["properties"].update(props)
    s["revision"] += 1


def reset_plots(key: str) -> None:
    """Forget the edits under this key; the next plot_editor call starts again from the features it is given."""
    st.session_state.pop(_skey(key), None)


# --- state ---------------------------------------------------------------------------------------------------------

def _skey(key):
    return f"_plot_editor_{key}"


def _state(key, features):
    k = _skey(key)
    if k not in st.session_state:
        st.session_state[k] = {"features": _clean(features), "selected": [], "history": [], "revision": 0,
                               "nonce": None, "message": None, "next": 1}
    s = st.session_state[k]
    _complete(s["features"])
    return s


def _complete(feats):
    """Every plot needs an id (the feature's own id, else its position) and an area in ha."""
    seen = set()
    for i, f in enumerate(feats):
        props = f.setdefault("properties", {})
        fid = str(props.get("id") or f.get("id") or f"p{i + 1}")
        while fid in seen:
            fid += "'"
        seen.add(fid)
        props["id"] = fid
        if props.get("ha") is None:
            props["ha"] = round(_metric(f).area / 1e4, 2)


# Basemaps that work without a key. CARTO (the look of st.pydeck_chart) now needs a free key from
# carto.com/basemaps/apikey: put carto_key = "..." in .streamlit/secrets.toml and it is used automatically.
_ESRI = {"tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"],
         "credit": "Tiles © Esri · Esri, HERE, Garmin, © OpenStreetMap contributors", "max_zoom": 16}


def _basemap():
    try:
        key = st.secrets.get("carto_key")
    except Exception:  # no secrets.toml at all
        key = None
    if key:
        return {"tiles": [f"https://basemaps.cartocdn.com/rastertiles/light_all/{{z}}/{{x}}/{{y}}@2x.png?key={key}"],
                "credit": "© OpenStreetMap contributors © CARTO", "max_zoom": 20}
    return _ESRI


def _clean(x):
    """Plain JSON (no numpy numbers, no tuples), and a copy, so the caller's features are never changed."""
    return json.loads(json.dumps(x, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def _remember(s):
    s["history"] = (s["history"] + [copy.deepcopy((s["features"], s["selected"]))])[-30:]


def _apply(s, event, lab, min_ha):
    """Run one action from the map. Returns True when the map needs drawing again."""
    action = event.get("action")
    if action == "select":
        s["selected"] = event.get("ids", [])
        return False
    s["message"] = None
    if action == "undo":
        if s["history"]:
            s["features"], s["selected"] = s["history"].pop()
    elif action == "paint":
        plans = event.get("plans", {})  # {plot id: crop key or None}, every paint the map has not seen confirmed
        _remember(s)
        for f in s["features"]:
            if f["properties"]["id"] in plans:
                f["properties"]["plan"] = plans[f["properties"]["id"]]
    elif action == "merge":
        s["message"] = _merge(s, event.get("ids", []), lab)
    elif action == "cut":
        s["message"] = _cut(s, event.get("line", []), lab, min_ha)
    else:
        return False
    s["revision"] += 1
    return True


# --- geometry ------------------------------------------------------------------------------------------------------

def _metric(f):
    return transform(_TO_M, shape(f["geometry"]))


def _feature(geom_m, props, fid):
    return {"type": "Feature", "id": fid, "geometry": _clean(mapping(transform(_TO_DEG, geom_m))),
            "properties": {**props, "id": fid, "ha": round(geom_m.area / 1e4, 2)}}


def _new_id(s, base):
    s["next"] += 1
    return f"{base}.{s['next']}"


def _merge(s, ids, lab):
    chosen = [f for f in s["features"] if f["properties"]["id"] in ids]
    if len(chosen) < 2:
        return None
    geoms = [_metric(f) for f in chosen]
    merged = unary_union([g.buffer(_SNAP_M, join_style="mitre") for g in geoms]).buffer(-_SNAP_M, join_style="mitre")
    if merged.geom_type != "Polygon":
        return lab["err_adjacent"]
    _remember(s)
    biggest = max(zip(geoms, chosen), key=lambda x: x[0].area)[1]  # the merged plot keeps the largest plot's crop
    props = dict(biggest["properties"])
    props["origin"] = sorted({o for f in chosen for o in f["properties"].get("origin", [f["properties"]["id"]])})
    new = _feature(merged, props, _new_id(s, str(props["origin"][0])))
    s["features"] = [f for f in s["features"] if f["properties"]["id"] not in ids] + [new]
    s["selected"] = [new["properties"]["id"]]
    return None


def _cut(s, coords, lab, min_ha):
    pts = [tuple(c[:2]) for c in coords]
    pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(pts) < 2:
        return lab["err_cut"]
    line = _stretch(transform(_TO_M, LineString(pts)), _REACH_M)
    out, cut_any, too_small = [], False, False
    for f in s["features"]:
        poly = _metric(f)
        pieces = [g for g in split(poly, line).geoms if g.area > 0] if line.intersects(poly) else [poly]
        if len(pieces) < 2:
            out.append(f)
        elif min(g.area for g in pieces) < min_ha * 1e4:
            out.append(f)
            too_small = True
        else:
            if not cut_any:
                _remember(s)
            cut_any = True
            props = dict(f["properties"])
            props.setdefault("origin", [props["id"]])
            out += [_feature(g, props, _new_id(s, str(props["id"])))
                    for g in sorted(pieces, key=lambda g: -g.area)]
    if cut_any:
        s["features"], s["selected"] = out, []
    if too_small:
        return lab["err_small"].format(ha=min_ha)
    return None if cut_any else lab["err_cut"]


def _stretch(line, d):
    """Push both ends of the line outwards by d metres along its first and last segment."""
    c = list(line.coords)

    def push(a, b):
        dx, dy = a[0] - b[0], a[1] - b[1]
        n = (dx * dx + dy * dy) ** 0.5 or 1.0
        return a[0] + dx / n * d, a[1] + dy / n * d

    c[0], c[-1] = push(c[0], c[1]), push(c[-1], c[-2])
    return LineString(c)
