"""Saved crop plans in Supabase, shared between planners: table public.crop_plans (see supabase_crop_plans.sql).

The Streamlit server talks to Supabase's REST API with the secret key from .streamlit/secrets.toml, so the key never
reaches a browser. Other farmers' plans are shown without their names: only outlines and crops, for the pressure maths.
"""
from __future__ import annotations

import datetime as dt

import requests
import streamlit as st

TABLE = "crop_plans"
FIRST, YEARS = 2026, 5  # the year chooser offers FIRST .. FIRST + YEARS - 1


def plan_years():
    return list(range(FIRST, FIRST + YEARS))


def _secret(*names):
    """A secret by any of its names, at the top of secrets.toml or inside a [supabase] section."""
    try:
        sec = st.secrets
        for name in names:
            if name in sec:
                return sec[name]
        for section in ("supabase", "SUPABASE"):
            if section in sec:
                for name in names + tuple(x.lower().removeprefix("supabase_") for x in names):
                    if name in sec[section]:
                        return sec[section][name]
    except Exception:  # no secrets.toml where Streamlit looks for it
        return None
    return None


def _cfg():
    url = _secret("SUPABASE_URL")
    key = _secret("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY")
    return (str(url).rstrip("/") if url else None), key


def available() -> bool:
    return all(_cfg())


def status() -> str:
    """Why saving works or not: "ok", "no_secrets" or "no_user"."""
    if not available():
        return "no_secrets"
    return "ok" if user_id() else "no_user"


def _headers(extra=None):
    _, key = _cfg()
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", **(extra or {})}


def user_id():
    """Who is saving: the logged-in account's id (or e-mail, username), None when nobody is logged in."""
    try:
        import accounts
        u = accounts.user()
    except Exception:
        return None
    if not u:
        return None
    get = (lambda k: u.get(k)) if isinstance(u, dict) else (lambda k: getattr(u, k, None))
    uid = next((get(k) for k in ("id", "user_id", "sub", "email", "username", "name") if get(k)), None)
    return str(uid) if uid else None


def _slim(features):
    """Only what a saved plan needs: outline, area and planned crop of each plot."""
    return [{"type": "Feature", "geometry": f["geometry"],
             "properties": {"id": f["properties"]["id"], "ha": f["properties"].get("ha"),
                            "plan": f["properties"].get("plan")}} for f in features]


def save(field_id: str, year: int, features: list[dict]) -> tuple[bool, str]:
    """Insert or replace this user's plan for one field and year."""
    url, _ = _cfg()
    uid = user_id()
    if not url or not uid:
        return False, "not configured" if not url else "not logged in"
    row = {"user_id": uid, "field_id": field_id, "year": int(year), "plots": _slim(features),
           "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    r = requests.post(f"{url}/rest/v1/{TABLE}", params={"on_conflict": "user_id,field_id,year"}, json=row,
                      headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}), timeout=15)
    if r.ok:
        plans_for_years.clear()
        return True, ""
    return False, f"{r.status_code}: {r.text[:200]}"


@st.cache_data(ttl=60, show_spinner=False)
def plans_for_years(years: tuple[int, ...]) -> list[dict]:
    """Every saved plan for these years (all users): [{user_id, field_id, year, plots, updated_at}]."""
    url, _ = _cfg()
    if not url:
        return []
    r = requests.get(f"{url}/rest/v1/{TABLE}", headers=_headers(),
                     params={"select": "user_id,field_id,year,plots,updated_at",
                             "year": f"in.({','.join(str(y) for y in years)})"}, timeout=15)
    return r.json() if r.ok else []


def mine(field_id: str, years) -> dict[int, list[dict]]:
    """This user's saved plots per year for one field: {year: features}."""
    uid = user_id()
    return {p["year"]: p["plots"] for p in plans_for_years(tuple(years))
            if uid and p["user_id"] == uid and p["field_id"] == field_id}


def others(field_id: str, years) -> list[dict]:
    """Everyone else's saved plans for these years (not this user's plan for this field)."""
    uid = user_id()
    return [p for p in plans_for_years(tuple(years)) if not (p["user_id"] == uid and p["field_id"] == field_id)
            and p["field_id"] != field_id]
