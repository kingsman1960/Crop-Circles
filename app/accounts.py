"""Accounts, farms and the neighbourhood feed, in one SQLite file (app/platform.db, created and seeded on first run).

How it fits the rest of the app
- app.py calls gate() on every platform page: no account in the session -> the sign-in card, and the page stops there.
- data.field_picker() asks my_fields() which field ids the account may open, so *My field* and *What to grow* show a
  farmer only their own field(s) and the advisor / office / admin every field.
- views/landscape.py lets a farmer add any FIONA parcel of the region map to their farm (toggle_parcel); views/field.py
  lists those parcels (my_parcels).
- views/community.py is the feed: post(), reply(), feed(); accounts() and delete_post() are the administrator's tools.

Roles: farmer (own fields), advisor (all fields), authority (the plant-protection office: all fields, answers alerts),
admin (all fields, sees the accounts table, can delete posts). Everything else in the app ignores roles.

Demo accounts are seeded below (password "demo" for all) so the platform can be shown with one farmer per demo field.
A real deployment swaps the sign-in card for st.login (OIDC) and keeps the rest; it also points DB at a hosted
database, because Streamlit Community Cloud forgets local files on every redeploy. No e-mail is sent by this module:
the feed prepares a mailto link the farmer sends themself.
"""
import hashlib
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from i18n import t

DB = Path(__file__).parent / "platform.db"  # gitignored; delete it to reset accounts, farms and posts
REGION = "Kraichgau"  # every account is in one region for now; the feed is per region
DEMO = [  # name, display, role, fields (farmers); advisor, office and admin see every field
    ("demo", "Demo farm", "farmer", "F1 F2 F3"),
    ("anna", "Anna Weber", "farmer", "F1"), ("jonas", "Jonas Keller", "farmer", "F2"), ("lea", "Lea Hoffmann", "farmer", "F3"),
    ("berater", "Sabine Roth", "advisor", ""), ("amt", "Pflanzenschutzdienst", "authority", ""), ("admin", "Administrator", "admin", "")]
DEMO_PASSWORD = "demo"
# user_fields: which demo field (F1..F3) a farmer owns. parcels: FIONA parcel ids added from the region map.
# posts.kind: note | question | alert. posts.field: a demo field id or "". Times are ISO 8601 in UTC.
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (name TEXT PRIMARY KEY, display TEXT, role TEXT, region TEXT, salt BLOB, hash BLOB);
CREATE TABLE IF NOT EXISTS user_fields (user TEXT, field TEXT, PRIMARY KEY (user, field));
CREATE TABLE IF NOT EXISTS parcels (user TEXT, parcel INTEGER, added TEXT, PRIMARY KEY (user, parcel));
CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, author TEXT, region TEXT, kind TEXT, field TEXT, text TEXT, created TEXT);
CREATE TABLE IF NOT EXISTS replies (id INTEGER PRIMARY KEY, post INTEGER, author TEXT, text TEXT, created TEXT);
"""


def _hash(pw, salt):
    """Password hash: PBKDF2-SHA256 with a per-user salt (stdlib; no password is stored in clear)."""
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)


def db():
    """A connection to the platform file; creates the tables and the demo accounts on first use.
    Opening a connection per call is cheap for SQLite and avoids sharing one across Streamlit threads."""
    con = sqlite3.connect(DB, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM users").fetchone():
        for name, display, role, field in DEMO:
            salt = secrets.token_bytes(16)
            con.execute("INSERT INTO users VALUES (?,?,?,?,?,?)", (name, display, role, REGION, salt, _hash(DEMO_PASSWORD, salt)))
            for f in field.split():
                con.execute("INSERT INTO user_fields VALUES (?,?)", (name, f))
        con.commit()
    return con


def now():
    """Timestamp for posts and replies; the page converts it to the reader's local time."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- who is here -------------------------------------------------------------------
def user():
    """The signed-in account as a dict (name, display, role, region), or None.
    The account name lives in st.session_state["user"], so it lasts for one browser session (a reload signs out)."""
    name = st.session_state.get("user")
    row = db().execute("SELECT name, display, role, region FROM users WHERE name = ?", (name,)).fetchone() if name else None
    return dict(row) if row else None


def sign_in(name, password):
    """True and the session is signed in when the password matches; compare_digest keeps the timing constant."""
    row = db().execute("SELECT salt, hash FROM users WHERE name = ?", (name.strip().lower(),)).fetchone()
    if row and secrets.compare_digest(_hash(password, row["salt"]), row["hash"]):
        st.session_state.user = name.strip().lower()
        return True
    return False


def gate():
    """The login card; stops the page until someone is signed in."""
    if user():
        return
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid.container(key="card_login"):
        st.subheader(t("login.title"))
        st.caption(t("login.intro"))
        with st.form("login", border=False):
            name = st.text_input(t("login.name"))
            pw = st.text_input(t("login.password"), type="password")
            if st.form_submit_button(t("login.go"), type="primary") and not sign_in(name, pw):
                st.error(t("login.wrong"))
            elif user():
                st.rerun()
        who = lambda role: ", ".join(n for n, _, r, _ in DEMO if r == role)
        st.markdown(t("login.demo", farmers=who("farmer"), advisor=who("advisor"), office=who("authority"), admin=who("admin"),
                      password=DEMO_PASSWORD))
    st.stop()


def sign_out():
    """Forget the account and the chosen field (the next account may not own it)."""
    st.session_state.pop("user", None)
    st.session_state.pop("field", None)


def my_fields(all_ids):
    """Field ids this account may open: a farmer's own, everything for advisors and the office."""
    u = user()
    if not u:
        return list(all_ids)
    if u["role"] != "farmer":
        return list(all_ids)
    own = [r["field"] for r in db().execute("SELECT field FROM user_fields WHERE user = ?", (u["name"],))]
    return [f for f in all_ids if f in own] or list(all_ids)[:1]  # a farmer without a demo field still sees one page


def display(name):
    """(display name, role) of an account, for the feed; unknown names fall back to the name itself."""
    row = db().execute("SELECT display, role FROM users WHERE name = ?", (name,)).fetchone()
    return (row["display"], row["role"]) if row else (name, "farmer")


# --- parcels a farmer adds from the region map ----------------------------------------
def my_parcels():
    """FIONA parcel ids the signed-in farmer added from the region map, oldest first."""
    u = user()
    return [r["parcel"] for r in db().execute("SELECT parcel FROM parcels WHERE user = ? ORDER BY added", (u["name"],))] if u else []


def toggle_parcel(pid):
    """Add the parcel to the farm, or remove it if it is already there (one button on the map does both)."""
    con, u = db(), user()
    if pid in my_parcels():
        con.execute("DELETE FROM parcels WHERE user = ? AND parcel = ?", (u["name"], pid))
    else:
        con.execute("INSERT INTO parcels VALUES (?,?,?)", (u["name"], pid, now()))
    con.commit()


# --- the feed ---------------------------------------------------------------------
def post(kind, field, text):
    """A new post in the account's region; kind is note | question | alert, field a demo field id or ""."""
    con = db()
    con.execute("INSERT INTO posts (author, region, kind, field, text, created) VALUES (?,?,?,?,?,?)",
                (user()["name"], user()["region"], kind, field or "", text.strip(), now()))
    con.commit()


def reply(post_id, text):
    """A reply under a post; an authority reply is what closes an alert (see views/community.py)."""
    con = db()
    con.execute("INSERT INTO replies (post, author, text, created) VALUES (?,?,?,?)", (post_id, user()["name"], text.strip(), now()))
    con.commit()


def feed(region, kinds=None):
    """Posts of a region, newest first, each with its replies (oldest first)."""
    con = db()
    q, args = "SELECT * FROM posts WHERE region = ?", [region]
    if kinds:
        q += f" AND kind IN ({','.join('?' * len(kinds))})"
        args += list(kinds)
    posts = [dict(r) for r in con.execute(q + " ORDER BY id DESC", args)]
    for p in posts:
        p["replies"] = [dict(r) for r in con.execute("SELECT * FROM replies WHERE post = ? ORDER BY id", (p["id"],))]
    return posts


# --- administration ------------------------------------------------------------------
def accounts():
    """Every account with its fields and post count, for the administrator's table."""
    con = db()
    return [dict(r) | {"fields": " ".join(f["field"] for f in con.execute("SELECT field FROM user_fields WHERE user = ? ORDER BY field", (r["name"],))),
                       "posts": con.execute("SELECT COUNT(*) FROM posts WHERE author = ?", (r["name"],)).fetchone()[0]}
            for r in con.execute("SELECT name, display, role, region FROM users ORDER BY role, name")]


def delete_post(post_id):
    """Remove a post and its replies (administrator only; the page checks the role)."""
    con = db()
    con.execute("DELETE FROM replies WHERE post = ?", (post_id,))
    con.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    con.commit()


if __name__ == "__main__":  # self-check against a throwaway file
    DB = Path(__file__).parent / "platform_selfcheck.db"
    DB.unlink(missing_ok=True)
    con = db()
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == len(DEMO)
    salt, h = con.execute("SELECT salt, hash FROM users WHERE name = 'anna'").fetchone()
    assert _hash("demo", salt) == h and _hash("x", salt) != h
    con.close()
    DB.unlink()
    print("accounts.py ok")
