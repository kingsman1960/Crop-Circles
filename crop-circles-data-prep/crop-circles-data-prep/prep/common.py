"""Shared helpers for the fetch scripts: config, polite HTTP, MANIFEST logging."""
import csv
import hashlib
import json
import math
import netrc
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "study_area.json"
RAW = ROOT / "data" / "raw"
MANIFEST = ROOT / "data" / "MANIFEST.csv"
MANIFEST_HEADER = ["file_path", "dataset_id", "source", "product_version", "query_or_url", "spatial", "temporal",
                   "downloaded_at_utc", "size_bytes", "sha256", "license", "attribution"]
UA = "crop-circles-data-prep (NASA Space Apps 2026 team)"
R_EARTH = 6371008.8
SESSION = requests.Session()  # keep-alive: one TLS handshake per host, not per request
sys.stdout.reconfigure(encoding="utf-8")  # Windows console default (cp949) cannot print umlauts


def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def http(method, url, pause=1.0, tries=5, **kw):
    """Request with retry + exponential backoff; sleeps `pause` s after every call."""
    kw.setdefault("timeout", 300)
    kw.setdefault("headers", {}).setdefault("User-Agent", UA)
    for attempt in range(tries):
        try:
            r = SESSION.request(method, url, **kw)
            if r.status_code < 500 and r.status_code != 429:
                time.sleep(pause)
                if not r.ok:
                    print(f"  HTTP {r.status_code}: {r.text[:500]}")
                r.raise_for_status()
                return r
            print(f"  HTTP {r.status_code} for {url[:100]}")
        except requests.ConnectionError as e:
            print(f"  {type(e).__name__} for {url[:100]}")
        time.sleep(10 * 2 ** attempt)
    r.raise_for_status()


def manifest_row(path, dataset_id, **kw):
    """One MANIFEST row for a downloaded file (size + sha256 computed here)."""
    path = Path(path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"file_path": path.relative_to(ROOT).as_posix(), "dataset_id": dataset_id,
            "size_bytes": path.stat().st_size, "sha256": h.hexdigest(), **kw}


def write_manifest(new_rows):
    """Add rows to MANIFEST; a re-download replaces the file's old row. One rewrite per call."""
    paths = {r["file_path"] for r in new_rows}
    rows = []
    if MANIFEST.exists():
        with MANIFEST.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["file_path"] not in paths]
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, MANIFEST_HEADER)
        w.writeheader()
        w.writerows(rows + list(new_rows))


def log(path, dataset_id, **kw):
    write_manifest([manifest_row(path, dataset_id, **kw)])


def dist_km(lon1, lat1, lon2, lat2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h)) / 1000


# --- NASA AppEEARS (Earthdata login from ~/.netrc; never printed) ---
APPEEARS = "https://appeears.earthdatacloud.nasa.gov/api/"


def appeears_login():
    user, _, password = netrc.netrc().authenticators("urs.earthdata.nasa.gov")
    return http("POST", APPEEARS + "login", auth=(user, password)).json()["token"]


def appeears_task(token, task, state_file):
    """Submit `task` once; the task id is kept in `state_file` so a re-run resumes instead of resubmitting."""
    if state_file.exists():
        return json.loads(state_file.read_text())["task_id"]
    auth = {"Authorization": f"Bearer {token}"}
    task_id = http("POST", APPEEARS + "task", json=task, headers=auth).json()["task_id"]
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"task_id": task_id, "submitted_utc": now_utc(), "task": task}, indent=1))
    return task_id


def appeears_status(token, task_id):
    return http("GET", APPEEARS + f"task/{task_id}", headers={"Authorization": f"Bearer {token}"}).json()["status"]


def appeears_wait(token, task_id, every=60):
    while (status := appeears_status(token, task_id)) != "done":
        print(f"  {now_utc()} AppEEARS task {task_id}: {status}")
        if status == "error":
            raise RuntimeError(f"AppEEARS task {task_id} failed")
        time.sleep(every)


def appeears_download(token, task_id, dest, workers=4):
    """Download every file of a finished task into `dest`; returns [(path, url)].
    `workers` files at a time (downloads of finished results only: allowed by the user 2026-11-04; an HLS task has
    ~1,500 small files). A file already on disk with the bundle's size is kept, so a re-run resumes."""
    auth = {"Authorization": f"Bearer {token}"}

    def get(f):
        url = APPEEARS + f"bundle/{task_id}/{f['file_id']}"
        path = dest / f["file_name"]
        if not (path.exists() and path.stat().st_size == f.get("file_size")):
            path.parent.mkdir(parents=True, exist_ok=True)
            with http("GET", url, headers=auth, stream=True, pause=0.1) as r, path.open("wb") as fh:
                for chunk in r.iter_content(1 << 20):
                    fh.write(chunk)
        return path, url

    files = http("GET", APPEEARS + f"bundle/{task_id}", headers=auth).json()["files"]
    with ThreadPoolExecutor(workers) as pool:
        futures = [pool.submit(get, f) for f in files]
        try:
            return [fu.result() for fu in futures]
        except BaseException:
            pool.shutdown(cancel_futures=True)  # e.g. a dead token: don't send the remaining requests
            raise


def appeears_logout(token):
    http("POST", APPEEARS + "logout", headers={"Authorization": f"Bearer {token}"})
