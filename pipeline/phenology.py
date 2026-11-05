"""DWD crop phenology near Heilbronn -> phenology.parquet (regional median day of year per crop, phase, year)."""
import pandas as pd

from pipeline.common import RAW, out, check

PH = RAW / "dwd_phenology"
CROPS = {  # DWD file stem -> (Objekt_id, our crop key)
    "Winterweizen": (202, "winter_wheat"),
    "Wintergerste": (204, "winter_barley"),
    "Mais": (215, "maize"),
    "Zucker-Ruebe": (253, "sugar_beet"),
    "Winterraps": (205, "winter_rapeseed"),
}
PHASES = {10: "sowing", 12: "emergence", 13: "closed stand", 15: "shooting", 18: "heading",
          19: "milk ripeness", 21: "yellow ripeness", 24: "harvest", 65: "tassel"}


def main():
    stations = pd.read_csv(PH / "stations_selected.csv")
    stations = set(stations.loc[stations.reporter == "annual", "stationsid"])
    frames = []
    for stem, (objekt, crop) in CROPS.items():
        for f in [*PH.glob(f"annual_reporters_crops_historical/*_{stem}_*_hist.txt"),
                  *PH.glob(f"annual_reporters_crops_recent/*_{stem}_akt.txt")]:
            # columns: station; ref year; quality; object; phase; date; date QB; julian day; eor
            df = pd.read_csv(f, sep=";", skiprows=1, header=None, usecols=[0, 3, 4, 5],
                             names=["station", "objekt", "phase_id", "date"], encoding="latin1")
            df = df[df.station.isin(stations) & (df.objekt == objekt) & df.phase_id.isin(PHASES)]
            frames.append(df.assign(crop=crop))
    df = pd.concat(frames).drop_duplicates(["station", "crop", "phase_id", "date"])
    df["date"] = pd.to_datetime(df.date.astype(str), format="%Y%m%d")
    df = df[df.date.dt.year >= 2001]
    df = (df.assign(year=df.date.dt.year, doy=df.date.dt.day_of_year)
            .groupby(["crop", "phase_id", "year"])
            .agg(doy=("doy", "median"), n=("station", "nunique")).reset_index())
    df["phase"] = df.phase_id.map(PHASES)
    df.to_parquet(out("phenology.parquet"), index=False)
    check("phenology.parquet", df, "year")
    print(df.groupby(["crop", "phase"]).doy.median().unstack().round().to_string())


if __name__ == "__main__":
    main()
