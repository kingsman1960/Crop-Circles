"""Dataset 3 - dwd_climate: DWD daily climate (kl) for stations near the fields.

Selection: per field the 3 nearest stations that are still active and have >= MIN_YEARS of record,
plus every station (active or closed) within NEAR_KM of a field.
"""
import re
import zipfile

import pandas as pd

from common import RAW, dist_km, http, load_config, log, now_utc

BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/"
STATIONS_TXT = "KL_Tageswerte_Beschreibung_Stationen.txt"
MIN_YEARS, NEAR_KM = 20, 10
VARS = ["TMK", "TXK", "TNK", "RSK"]  # mean/max/min temperature at 2 m, precipitation height (DWD kl description)
OUT = RAW / "dwd_climate"
META = dict(source="DWD Climate Data Center, daily kl station observations", license="CC BY 4.0",
            attribution="Source: Deutscher Wetterdienst (DWD), Climate Data Center (CDC), CC BY 4.0")


def get(rel, dest=None):
    r = http("GET", BASE + rel, pause=1)
    if dest:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
    return r


def read_stations(path):
    # columns are not aligned with the dashed ruler; split on whitespace (Bundesland and Abgabe are single tokens)
    lines = path.read_text(encoding="latin1").splitlines()
    rows = [p[:6] + [" ".join(p[6:-2])] + p[-2:] for p in (l.split() for l in lines[2:]) if len(p) >= 9]
    df = pd.DataFrame(rows, columns=lines[0].split())
    for c in ("geoBreite", "geoLaenge", "Stationshoehe"):
        df[c] = df[c].astype(float)
    return df


def select(st, cfg):
    end = pd.Timestamp(cfg["period"]["end"])
    st = st.copy()
    for f in cfg["fields"]:
        st[f"dist_{f['id']}_km"] = [round(dist_km(f["lon"], f["lat"], x, y), 1) for x, y in zip(st.geoLaenge, st.geoBreite)]
    von, bis = pd.to_datetime(st.von_datum), pd.to_datetime(st.bis_datum)
    long_active = st[(bis >= end) & (von <= end - pd.DateOffset(years=MIN_YEARS))]
    reason = {}
    for f in cfg["fields"]:
        for sid in long_active.nsmallest(3, f"dist_{f['id']}_km").Stations_id:
            reason.setdefault(sid, []).append(f"3 nearest active >= {MIN_YEARS} yr to {f['id']}")
    dcols = [f"dist_{f['id']}_km" for f in cfg["fields"]]
    for sid in st[st[dcols].min(axis=1) <= NEAR_KM].Stations_id:
        reason.setdefault(sid, []).append(f"within {NEAR_KM} km of a field")
    sel = st[st.Stations_id.isin(reason)].copy()
    sel["selection"] = sel.Stations_id.map(lambda s: "; ".join(reason[s]))
    return sel


def read_produkt(path):
    df = pd.read_csv(path, sep=";", skipinitialspace=True, dtype={"STATIONS_ID": str})
    df.columns = df.columns.str.strip()
    df["date"] = pd.to_datetime(df.MESS_DATUM.astype(str), format="%Y%m%d")
    return df


def long_gaps(dates, days=30):
    """Periods > `days` without a valid value (dates = sorted dates that have a value)."""
    d = dates.sort_values().reset_index(drop=True)
    step = d.diff().dt.days
    return [(d[i - 1].date(), d[i].date(), int(step[i]) - 1) for i in step[step > days + 1].index]


def main():
    cfg = load_config()
    OUT.mkdir(parents=True, exist_ok=True)
    listing = {}
    for part in ("historical", "recent"):
        when = now_utc()
        p = OUT / f"{part}_{STATIONS_TXT}"
        get(f"{part}/{STATIONS_TXT}", p)
        log(p, "dwd_climate", query_or_url=BASE + f"{part}/{STATIONS_TXT}", spatial="Germany", temporal=part,
            downloaded_at_utc=when, product_version=part, **META)
        listing[part] = re.findall(r'href="(tageswerte_KL_[^"]+\.zip)"', get(f"{part}/").text)

    st = read_stations(OUT / f"historical_{STATIONS_TXT}")
    sel = select(st, cfg)
    p0, p1 = pd.Timestamp(cfg["period"]["start"]), pd.Timestamp(cfg["period"]["end"])
    summary = []
    for s in sel.itertuples():
        sid = s.Stations_id
        frames = []
        for part in ("historical", "recent"):
            for z in [z for z in listing[part] if f"_KL_{sid}_" in z]:
                when = now_utc()
                zp = OUT / sid / z
                r = get(f"{part}/{z}", zp)
                log(zp, "dwd_climate", query_or_url=r.url, spatial=f"station {sid} {s.Stationsname}",
                    temporal=part, downloaded_at_utc=when, product_version=part, **META)
                with zipfile.ZipFile(zp) as zf:
                    for name in [n for n in zf.namelist() if n.startswith("produkt_klima_tag_")]:
                        zf.extract(name, zp.parent)
                        log(zp.parent / name, "dwd_climate", query_or_url=f"extracted from {z}",
                            spatial=f"station {sid} {s.Stationsname}", temporal=part, downloaded_at_utc=when,
                            product_version=part, **META)
                        frames.append(read_produkt(zp.parent / name).assign(part=part))
        if not frames:
            print(f"{sid} {s.Stationsname}: no zip found")
            continue
        # historical (QC done) wins where historical and recent overlap
        df = pd.concat(frames).drop_duplicates("date", keep="first").sort_values("date")
        print(f"\n{sid} {s.Stationsname} ({s.selection}): {len(df)} days, {df.date.min().date()} -> {df.date.max().date()}")
        row = dict(station=sid, name=s.Stationsname, days=len(df), first=df.date.min().date(), last=df.date.max().date(),
                   power_overlap=f"{max(df.date.min(), p0).date()} -> {min(df.date.max(), p1).date()}")
        for v in VARS:
            ok = df.loc[df[v] != -999, "date"]
            gaps = long_gaps(ok)
            row[f"{v}_missing"] = int((df[v] == -999).sum())
            row[f"{v}_gaps>30d"] = len(gaps)
            span = f"{ok.min().date()} -> {ok.max().date()}" if len(ok) else "no data"
            print(f"  {v}: -999 x{row[f'{v}_missing']}, valid {span}, gaps >30 d: {gaps[:5]}{' ...' if len(gaps) > 5 else ''}")
        summary.append(row)

    sel = sel.rename(columns={"Stations_id": "station_id", "Stationsname": "name", "geoBreite": "lat", "geoLaenge": "lon",
                              "Stationshoehe": "height_m", "von_datum": "record_start", "bis_datum": "record_end"})
    sel = sel.drop(columns=[c for c in ("Bundesland", "Abgabe") if c in sel])
    sel.to_csv(OUT / "stations_selected.csv", index=False)
    print("\n" + pd.DataFrame(summary).to_string(index=False))


if __name__ == "__main__":
    main()
