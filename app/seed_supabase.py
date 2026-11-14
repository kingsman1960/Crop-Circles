"""One-time setup of the Supabase side: demo accounts, and optionally the old SQLite feed.

    python app/seed_supabase.py                                  # demo accounts only (safe to run again)
    python app/seed_supabase.py --import-sqlite app/platform.db  # also copy parcels, posts and replies

Run from the repo root after supabase/schema.sql. Keys are read from the environment or .streamlit/secrets.toml.
Old passwords cannot be moved (they were hashed), so every demo account gets accounts.DEMO_PASSWORD.
"""
import argparse
import os
import sqlite3
import tomllib
from pathlib import Path

from supabase import ClientOptions, create_client

from accounts import DEMO, DEMO_EMAIL_DOMAIN, DEMO_PASSWORD, REGION


def secret(key):
    if key in os.environ:
        return os.environ[key]
    path = Path(".streamlit/secrets.toml")
    if not path.exists():
        raise SystemExit(f"{key} is not set and {path.resolve()} does not exist (run this from the repo root)")
    return tomllib.loads(path.read_text())[key]


def seed_accounts(sb):
    existing = {u.email: u.id for u in sb.auth.admin.list_users(per_page=1000)}
    for name, display, role, fields in DEMO:
        email = f"{name}@{DEMO_EMAIL_DOMAIN}"
        uid = existing.get(email)
        if uid is None:
            uid = sb.auth.admin.create_user({"email": email, "password": DEMO_PASSWORD, "email_confirm": True}).user.id
        else:
            sb.auth.admin.update_user_by_id(uid, {"password": DEMO_PASSWORD})
        sb.table("profiles").upsert({"id": uid, "name": name, "email": email, "display": display, "role": role,
                                     "region": REGION}).execute()
        for f in fields.split():
            sb.table("user_fields").upsert({"account": name, "field": f}).execute()
        print(f"  {name:8} {role:9} {email}")


def import_sqlite(sb, path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    known = {r["name"] for r in sb.table("profiles").select("name").execute().data}

    parcels = [{"account": r["user"], "parcel": r["parcel"], "added": r["added"]}
               for r in con.execute("SELECT * FROM parcels") if r["user"] in known]
    if parcels:
        sb.table("parcels").upsert(parcels).execute()

    new_id = {}  # old post id -> new post id
    for r in con.execute("SELECT * FROM posts ORDER BY id"):
        if r["author"] not in known:
            continue
        row = sb.table("posts").insert({k: r[k] for k in ("author", "region", "kind", "field", "text", "created")}).execute().data[0]
        new_id[r["id"]] = row["id"]
    replies = [{"post": new_id[r["post"]], "author": r["author"], "text": r["text"], "created": r["created"]}
               for r in con.execute("SELECT * FROM replies ORDER BY id") if r["post"] in new_id and r["author"] in known]
    if replies:
        sb.table("replies").insert(replies).execute()
    print(f"  imported {len(parcels)} parcels, {len(new_id)} posts, {len(replies)} replies")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--import-sqlite", type=Path, help="old app/platform.db to copy parcels, posts and replies from")
    args = ap.parse_args()
    sb = create_client(secret("SUPABASE_URL"), secret("SUPABASE_SECRET_KEY"),
                       options=ClientOptions(auto_refresh_token=False, persist_session=False))
    print("Demo accounts:")
    seed_accounts(sb)
    if args.import_sqlite:
        if sb.table("posts").select("id").limit(1).execute().data:
            raise SystemExit("posts already has rows; not importing twice")
        import_sqlite(sb, args.import_sqlite)
    print("done")
