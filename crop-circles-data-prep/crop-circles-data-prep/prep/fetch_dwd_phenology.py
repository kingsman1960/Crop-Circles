"""Dataset 4 - dwd_phenology: DWD crop phenology (annual + immediate reporters), Germany-wide files kept as downloaded.

Station selection (stations_selected.csv) and the check use the centre/radius in config "phenology".
Soybean is not observed in the DWD crop programme (no file exists).
"""
import re

import pandas as pd

from common import RAW, dist_km, http, load_config, log, now_utc

PH = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/phenology/"
HELP = "https://opendata.dwd.de/climate_environment/CDC/help/"
# crop -> (annual file stems, immediate file stems); "Ruebe" files cover several beet types, see Ruebe_Spezifizierung
CROPS = {"winter wheat": (["Winterweizen"], ["Winterweizen"]),
         "winter barley": (["Wintergerste"], ["Wintergerste"]),
         "sugar beet": (["Zucker-Ruebe", "Ruebe"], ["Ruebe"]),
         "maize": (["Mais"], ["Mais_ohne_Sortenangabe"]),
         "winter rapeseed": (["Winterraps"], ["Winterraps"])}
DOCS = [HELP + "PH_Beschreibung_Phaenologie_Stationen_Jahresmelder.txt",
        HELP + "PH_Beschreibung_Phaenologie_Stationen_Sofortmelder.txt",
        HELP + "PH_Beschreibung_Phase.txt",
        HELP + "PH_Beschreibung_Pflanze.txt",
        PH + "annual_reporters/crops/recent/PH_Beschreibung_Phasendefinition_Jahresmelder_Landwirtschaft_Kulturpflanze.txt",
        PH + "annual_reporters/crops/recent/PH_Jahresmelder_Landwirtschaft_Kulturpflanze_Ruebe_Spezifizierung.txt",
        PH + "immediate_reporters/crops/recent/PH_Beschreibung_Phasendefinition_Sofortmelder_Landwirtschaft_Kulturpflanze.txt"]
OUT = RAW / "dwd_phenology"
META = dict(source="DWD Climate Data Center, phenological observations of crops", license="CC BY 4.0",
            attribution="Source: Deutscher Wetterdienst (DWD), Climate Data Center (CDC), CC BY 4.0")


def download(url, sub):
    path = OUT / sub / url.rsplit("/", 1)[1]
    if path.exists() and path.name.endswith("_hist.txt"):  # historical releases never change
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    when = now_utc()
    with http("GET", url, stream=True) as r, path.open("wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    log(path, "dwd_phenology", query_or_url=url, spatial="Germany", temporal=sub, downloaded_at_utc=when,
        product_version=sub, **META)
    return path


def table(path):
    """DWD ';'-separated text with padded fields and a trailing 'eor' column.
    Header spelling differs between files (Stations_id / STATIONS_ID, Referenzjahr / REFERENZ_JAHR): normalised."""
    df = pd.read_csv(path, sep=";", encoding="latin1", dtype=str, skipinitialspace=True)
    df.columns = df.columns.str.strip().str.lower().str.replace("_", "")
    df = df.drop(columns=[c for c in df.columns if c in ("eor", "") or c.startswith("unnamed")])
    df = df.apply(lambda s: s.str.strip())
    df["stationsid"] = df.stationsid.astype(int)  # station list is zero-padded, data files are not
    return df


def lookup(path):
    """id -> (German, English) from PH_Beschreibung_Phase/Pflanze (records end with 'eor;')."""
    recs = [r.split(";") for r in path.read_text(encoding="latin1").split("eor;")[1:]]
    return {int(r[0]): (r[1].strip(), r[2].strip()) for r in recs if len(r) > 2 and r[0].strip().isdigit()}


def main():
    cfg = load_config()
    c = cfg["phenology"]
    docs = {u.rsplit("/", 1)[1]: download(u, "docs") for u in DOCS}

    parts = ("annual_reporters/crops/historical/", "annual_reporters/crops/recent/", "immediate_reporters/crops/recent/")
    listing = {part: re.findall(r'href="(PH_[^"]+\.txt)"', http("GET", PH + part).text) for part in parts}
    files = []  # (crop, reporter, path)
    for crop, (annual, immediate) in CROPS.items():
        for part, stems in zip(parts, (annual, annual, immediate)):
            names = listing[part]
            for stem in stems:
                hits = sorted(n for n in names if re.fullmatch(rf"PH_\w+_Kulturpflanze_{re.escape(stem)}_(\d{{4}}_\d{{4}}_hist|akt)\.txt", n))
                if hits:  # historical: several releases exist (…_2018, _2019, _2024); the latest end year wins
                    hist = [n for n in hits if n.endswith("_hist.txt")]
                    name = max(hist, key=lambda n: n.split("_")[-2]) if hist else hits[0]
                    reporter = "immediate" if part.startswith("immediate") else "annual"
                    files.append((crop, reporter, download(PH + part + name, part.strip("/").replace("/", "_"))))

    # stations within the radius
    st = pd.concat([table(docs[f"PH_Beschreibung_Phaenologie_Stationen_{k}.txt"]).assign(reporter=v)
                    for k, v in (("Jahresmelder", "annual"), ("Sofortmelder", "immediate"))])
    st["lat"], st["lon"] = st["geograph.breite"].astype(float), st["geograph.laenge"].astype(float)
    st[f"dist_{c['center']}_km"] = [round(dist_km(c["lon"], c["lat"], x, y), 1) for x, y in zip(st.lon, st.lat)]
    for f in cfg["fields"]:
        st[f"dist_{f['id']}_km"] = [round(dist_km(f["lon"], f["lat"], x, y), 1) for x, y in zip(st.lon, st.lat)]
    near = st[st[f"dist_{c['center']}_km"] <= c["radius_km"]]

    phases, plants = lookup(docs["PH_Beschreibung_Phase.txt"]), lookup(docs["PH_Beschreibung_Pflanze.txt"])
    obs = []
    for crop, reporter, path in files:
        df = table(path)
        df = df[df.stationsid.isin(near.stationsid)]
        obs.append(df.assign(crop=crop, reporter=reporter, file=path.name))
        print(f"{path.name}: {len(df)} rows within {c['radius_km']} km")
    obs = pd.concat(obs)
    obs["year"] = obs.referenzjahr.astype(int)
    used = near[near.set_index(["stationsid", "reporter"]).index.isin(
        obs.set_index(["stationsid", "reporter"]).index.unique())]
    keep = ["stationsid", "reporter", "stationsname", "lat", "lon", "stationshoehe", f"dist_{c['center']}_km"] + \
           [f"dist_{f['id']}_km" for f in cfg["fields"]]
    used[keep].sort_values(f"dist_{c['center']}_km").to_csv(OUT / "stations_selected.csv", index=False)
    print(f"\nstations within {c['radius_km']} km of {c['center']}: {len(near)} listed, {len(used)} with crop data "
          f"-> stations_selected.csv")

    # check: station-years per crop and phase since 2001 (annual = historical + recent, deduplicated)
    o = obs[obs.year >= 2001].copy()
    o["objektid"], o["phaseid"] = o.objektid.astype(int), o.phaseid.astype(int)
    o = o.drop_duplicates(["reporter", "stationsid", "year", "objektid", "phaseid"])
    o["object"] = o.objektid.map(lambda i: plants.get(i, ("?", "?"))[1])
    # the annual "Ruebe" file mixes beet types; the Spezifizierung file names the variety per station-year
    spec = table(docs["PH_Jahresmelder_Landwirtschaft_Kulturpflanze_Ruebe_Spezifizierung.txt"])
    spec["year"] = spec.referenzjahr.astype(int)
    o = o.merge(spec[["stationsid", "year", "sorte"]].drop_duplicates(["stationsid", "year"]), how="left")
    ruebe = o.file.str.contains("_Ruebe_akt") & (o.reporter == "annual")
    o.loc[ruebe, "object"] = o.object + " / " + o.sorte.fillna("variety ?")
    o["phase"] = o.phaseid.map(lambda i: phases.get(i, ("?", "?"))[1])
    chk = o.groupby(["crop", "object", "phaseid", "phase", "reporter"]).agg(
        station_years=("year", "size"), stations=("stationsid", "nunique"), first=("year", "min"), last=("year", "max"))
    print("\n" + chk.unstack("reporter").to_string())


if __name__ == "__main__":
    main()
