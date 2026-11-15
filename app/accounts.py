"""Accounts, farms and the neighbourhood feed, on Supabase (Auth for sign-in, Postgres for the data).

How it fits the rest of the app (unchanged from the SQLite version: same functions, same return shapes)
- app.py calls gate() on every platform page: no account in the session -> the sign-in card, and the page stops there.
- data.field_picker() asks my_fields() which field ids the account may open, so *My field* and *What to grow* show a
  farmer only their own field(s) and the advisor / office / admin every field.
- views/landscape.py lets a farmer add any FIONA parcel of the region map to their farm (toggle_parcel); views/field.py
  lists those parcels (my_parcels).
- views/community.py is the feed: post(), reply(), feed(); accounts() and delete_post() are the administrator's tools.

Roles: farmer (own fields), advisor (all fields), authority (the plant-protection office: all fields, answers alerts),
admin (all fields, sees the accounts table, can delete posts). Everything else in the app ignores roles.

Sign-in and sessions
- Supabase Auth checks the password (by account name or e-mail) and returns an access token (about 1 h) and a
  refresh token. Both stay in st.session_state on the server; the access token is verified locally against the
  project's JWKS and renewed with the refresh token shortly before it expires.
- The refresh token is also written to a cookie, so a browser reload (a new Streamlit session) signs straight back
  in: user() reads it with st.context.cookies and swaps it for fresh tokens. Sign-out revokes it at Supabase.
- All table access runs on the server with the secret key; RLS is on with no policies, so the publishable key
  cannot read the tables. The secret key never reaches the browser.

Setup: run supabase/schema.sql once in the Supabase SQL editor, then `python app/seed_supabase.py` for the demo
accounts. Keys come from st.secrets (.streamlit/secrets.toml locally, the app's Secrets on Community Cloud).
"""
import json
import time
from datetime import datetime, timezone
from urllib.parse import unquote

import jwt
import streamlit as st
import streamlit.components.v1 as components
from supabase import ClientOptions, create_client

from i18n import t

REGION = "Kraichgau"  # every account is in one region for now; the feed is per region
DEMO = [  # name, display, role, fields (farmers); advisor, office and admin see every field
    ("demo", "Demo farm", "farmer", "F1 F2 F3"),
    ("anna", "Anna Weber", "farmer", "F1"), ("jonas", "Jonas Keller", "farmer", "F2"), ("lea", "Lea Hoffmann", "farmer", "F3"),
    ("berater", "Sabine Roth", "advisor", ""), ("amt", "Pflanzenschutzdienst", "authority", ""), ("admin", "Administrator", "admin", "")]
DEMO_PASSWORD = "demo1234"  # Supabase Auth needs at least 6 characters
DEMO_EMAIL_DOMAIN = "demo.cropcircles.app"  # demo accounts sign in as <name>@this domain; no mail is ever sent there
COOKIE = "cc_session"  # holds the Supabase refresh token
COOKIE_DAYS = 30
_NO_CLIENT_REFRESH = ClientOptions(auto_refresh_token=False, persist_session=False)  # no background threads per client


# --- Supabase clients ---------------------------------------------------------------
@st.cache_resource
def _db():
    """Server-side client with the secret key: all table reads and writes, and the auth admin calls.
    Never sign a user in on this client; it is shared by every session."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"], options=_NO_CLIENT_REFRESH)


def _auth():
    """A fresh client with the publishable key for one sign-in or refresh call. Not cached: a supabase client
    remembers the session it signed in, and sessions must not leak between users."""
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_PUBLISHABLE_KEY"], options=_NO_CLIENT_REFRESH)


@st.cache_resource
def _jwks():
    """Supabase's public signing keys (fetched once, refreshed by PyJWT when a new key id shows up)."""
    return jwt.PyJWKClient(st.secrets["SUPABASE_JWKS_URL"])


def _claims(token):
    """Verified claims of an access token; raises jwt.InvalidTokenError (incl. ExpiredSignatureError)."""
    key = _jwks().get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["ES256", "RS256"], audience="authenticated")


def now():
    """Timestamp for posts and replies; the page converts it to the reader's local time."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --- session handling -----------------------------------------------------------------
def _queue_cookie(value, max_age):
    """Remember a cookie change; gate() writes it to the browser on its next run (see _flush_cookie)."""
    st.session_state["_cookie"] = (value, max_age)


def _flush_cookie():
    """Write a queued cookie through a zero-height component (Streamlit can read cookies but not set them)."""
    op = st.session_state.pop("_cookie", None)
    if op is None:
        return
    value, max_age = op
    components.html(
        "<script>"
        f"const v = encodeURIComponent({json.dumps(value)});"
        "const secure = parent.location.protocol === 'https:' ? '; Secure' : '';"
        f"parent.document.cookie = '{COOKIE}=' + v + '; Max-Age={int(max_age)}; Path=/; SameSite=Strict' + secure;"
        "</script>", height=0)


def _start(session):
    """Store a fresh Supabase session plus the account's profile and fields. False if the auth user has no profile."""
    rows = _db().table("profiles").select("name, display, role, region").eq("id", session.user.id).execute().data
    if not rows:
        return False
    profile = rows[0]
    fields = [r["field"] for r in _db().table("user_fields").select("field").eq("account", profile["name"]).execute().data]
    st.session_state.auth = {"access": session.access_token, "refresh": session.refresh_token, "profile": profile, "fields": fields}
    st.session_state.user = profile["name"]  # kept for code that read the old key
    _queue_cookie(session.refresh_token, COOKIE_DAYS * 86400)
    return True


def _refresh(refresh_token):
    """Swap a refresh token for a new session, or None if Supabase refuses it (revoked, expired, already used)."""
    try:
        return _auth().auth.refresh_session(refresh_token).session
    except Exception:
        return None


def _forget():
    """Drop the session on this side and delete the cookie in the browser."""
    st.session_state.pop("auth", None)
    st.session_state.pop("user", None)
    st.session_state.pop("field", None)  # the next account may not own the chosen field
    st.session_state["_no_restore"] = True  # this browser session's cookie snapshot is stale now
    _queue_cookie("", 0)


def _restore():
    """Sign back in from the cookie after a reload. Tried once per Streamlit session."""
    if st.session_state.get("_no_restore"):
        return None
    st.session_state["_no_restore"] = True
    token = st.context.cookies.get(COOKIE)
    if not token:
        return None
    session = _refresh(unquote(token))
    if session and _start(session):
        return st.session_state.auth
    _queue_cookie("", 0)
    return None


# --- who is here -------------------------------------------------------------------
def user():
    """The signed-in account as a dict (name, display, role, region), or None.
    Survives a browser reload through the session cookie; renews the access token a minute before it runs out."""
    s = st.session_state.get("auth") or _restore()
    if not s:
        return None
    try:
        expiring = _claims(s["access"])["exp"] - time.time() < 60
    except jwt.ExpiredSignatureError:
        expiring = True
    except jwt.InvalidTokenError:
        _forget()
        return None
    if expiring:
        session = _refresh(s["refresh"])
        if not session:
            _forget()
            return None
        s.update(access=session.access_token, refresh=session.refresh_token)  # refresh tokens rotate: store the new one
        _queue_cookie(session.refresh_token, COOKIE_DAYS * 86400)
    return dict(s["profile"])


def sign_in(name, password):
    """True and the session is signed in when the password matches. Accepts the account name or the e-mail."""
    login = name.strip().lower()
    if "@" not in login:
        rows = _db().table("profiles").select("email").eq("name", login).execute().data
        if not rows:
            return False
        login = rows[0]["email"]
    try:
        session = _auth().auth.sign_in_with_password({"email": login, "password": password}).session
    except Exception:  # wrong password, unknown e-mail, rate limit: the card shows one message for all
        return False
    if not session or not _start(session):
        return False
    st.session_state.pop("_no_restore", None)
    return True


def gate():
    """The login card; stops the page until someone is signed in."""
    if user():
        _flush_cookie()
        return
    _flush_cookie()  # e.g. the delete after a sign-out or a refused cookie
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
    """Revoke the session at Supabase, forget it here and delete the cookie."""
    s = st.session_state.get("auth")
    if s:
        try:
            _db().auth.admin.sign_out(s["access"])
        except Exception:
            pass  # an expired token cannot be revoked this way; the cookie is deleted either way
    _forget()


def my_fields(all_ids):
    """Field ids this account may open: a farmer's own, everything for advisors and the office."""
    u = user()
    if not u or u["role"] != "farmer":
        return list(all_ids)
    own = st.session_state.auth["fields"]
    return [f for f in all_ids if f in own] or list(all_ids)[:1]  # a farmer without a demo field still sees one page


@st.cache_data(ttl=600)
def _profiles():
    """name -> (display, role) for every account; cached so the feed does not ask once per post."""
    return {r["name"]: (r["display"], r["role"]) for r in _db().table("profiles").select("name, display, role").execute().data}


def display(name):
    """(display name, role) of an account, for the feed; unknown names fall back to the name itself."""
    return _profiles().get(name, (name, "farmer"))


# --- parcels a farmer adds from the region map ----------------------------------------
def my_parcels():
    """FIONA parcel ids the signed-in farmer added from the region map, oldest first."""
    u = user()
    if not u:
        return []
    rows = _db().table("parcels").select("parcel").eq("account", u["name"]).order("added").execute().data
    return [r["parcel"] for r in rows]


def toggle_parcel(pid):
    """Add the parcel to the farm, or remove it if it is already there (one button on the map does both)."""
    u = user()
    table = _db().table("parcels")
    if pid in my_parcels():
        table.delete().eq("account", u["name"]).eq("parcel", pid).execute()
    else:
        table.insert({"account": u["name"], "parcel": int(pid), "added": now()}).execute()


# --- the feed ---------------------------------------------------------------------
def post(kind, field, text):
    """A new post in the account's region; kind is note | question | alert, field a demo field id or ""."""
    u = user()
    _db().table("posts").insert({"author": u["name"], "region": u["region"], "kind": kind, "field": field or "",
                                 "text": text.strip(), "created": now()}).execute()


def reply(post_id, text):
    """A reply under a post; an authority reply is what closes an alert (see views/community.py)."""
    _db().table("replies").insert({"post": post_id, "author": user()["name"], "text": text.strip(), "created": now()}).execute()


def feed(region, kinds=None):
    """Posts of a region, newest first, each with its replies (oldest first). One request for posts and replies."""
    q = _db().table("posts").select("*, replies(*)").eq("region", region)
    if kinds:
        q = q.in_("kind", list(kinds))
    posts = q.order("id", desc=True).execute().data
    for p in posts:
        p["replies"] = sorted(p.get("replies") or [], key=lambda r: r["id"])
    return posts


# --- administration ------------------------------------------------------------------
def accounts():
    """Every account with its fields and post count, for the administrator's table."""
    db = _db()
    fields, counts = {}, {}
    for r in db.table("user_fields").select("account, field").order("field").execute().data:
        fields.setdefault(r["account"], []).append(r["field"])
    for r in db.table("posts").select("author").execute().data:
        counts[r["author"]] = counts.get(r["author"], 0) + 1
    users = db.table("profiles").select("name, display, role, region").order("role").order("name").execute().data
    return [u | {"fields": " ".join(fields.get(u["name"], [])), "posts": counts.get(u["name"], 0)} for u in users]


def update_post(post_id, text):
    """Rewrite a post's text. Author only: the author filter makes the request a no-op for anyone else."""
    _db().table("posts").update({"text": text.strip()}).eq("id", post_id).eq("author", user()["name"]).execute()


def delete_post(post_id):
    """Remove a post; its replies go with it (on delete cascade). Administrator only; the page checks the role."""
    _db().table("posts").delete().eq("id", post_id).execute()
