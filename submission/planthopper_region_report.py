"""The region-wide planthopper edge test as a PDF report (English): python submission/planthopper_region_report.py
Reads planthopper_effect/region_summary.json and the hls_region parcel series; writes submission/planthopper_region_report.pdf."""
import json
import sys
import textwrap
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # the repo root, for `pipeline`

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from pipeline.common import PROC, RAW
from pipeline.planthopper_region import CELL, R_GRID, soil, windows

OUT = Path(__file__).with_suffix(".pdf")
INK, PINK, GREY, POS = "#16213e", "#b03a72", "#7a8496", "#2f7d5b"
LABEL = {"ndvi": "NDVI", "gndvi": "GNDVI", "ndre": "NDRE"}
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GREY, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "axes.titleweight": "bold", "axes.titlesize": 10})


def text_page(pdf, title, blocks, subtitle=None):
    """One A4 page of wrapped text: blocks are (heading or None, paragraph) pairs."""
    fig = plt.figure(figsize=(8.27, 11.69))
    y = 0.95
    fig.text(0.08, y, title, fontsize=15, fontweight="bold", color=INK, va="top")
    y -= 0.035
    if subtitle:
        fig.text(0.08, y, subtitle, fontsize=9.5, color=GREY, va="top")
        y -= 0.03
    for head, para in blocks:
        if head:
            y -= 0.012
            fig.text(0.08, y, head, fontsize=11, fontweight="bold", color=INK, va="top")
            y -= 0.028
        for line in textwrap.wrap(para, 98) if para else [""]:
            fig.text(0.08, y, line, fontsize=9.2, color=INK, va="top")
            y -= 0.0185
        y -= 0.008
    pdf.savefig(fig)
    plt.close(fig)


def main():
    r = json.loads((PROC / "planthopper_effect" / "region_summary.json").read_text(encoding="utf-8"))
    parcels = soil(pd.concat([pd.read_parquet(p) for p in sorted((RAW / "hls_region").glob("parcels_*.parquet"))], ignore_index=True))
    series = pd.concat([pd.read_parquet(p).assign(year=lambda d: d.date.dt.year)
                        for p in sorted((RAW / "hls_region").glob("series_*.parquet"))], ignore_index=True)
    meta = parcels.set_index(["id", "year"])
    d = {k: windows(series.dropna(subset=[k]), k).join(meta[["role", "dist_to_source", "x", "y", "ks", "nfk_mm"]], how="inner").reset_index()
         for k in LABEL}
    n_total, n_adj = len(d["ndre"]), int((d["ndre"].role == "nursery_adjacent").sum())
    ix = r["index"]

    with PdfPages(OUT) as pdf:
        # --- 1. summary ------------------------------------------------------------------------------------------
        text_page(pdf, "Beet next to a planthopper nursery loses more canopy",
                  [(None, f"Crop Circles · NASA Space Apps Challenge 2026 (Field Shift) · Heilbronn / Kraichgau, Baden-Württemberg · {date.today():%d %B %Y}"),
                   ("Question", "The reed planthopper (Pentastiridius leporinus) overwinters as nymphs in winter wheat sown after sugar beet "
                                "(the \"nursery\"); the adults fly into the surrounding beet in June and transmit SBR / Stolbur. JKI, LIZ and LLG "
                                "therefore advise against wheat directly after beet. Does the landscape show the effect? Do beet parcels that "
                                "lie next to a nursery decline more between June and late summer than beet parcels next to other winter wheat?"),
                   ("Answer", f"Yes, consistently. Across {n_total:,} declared sugar-beet parcel-seasons (2023–2025), beet within 50 m of a nursery "
                              f"lost more canopy from June to late summer than beet within 50 m of control wheat (and at least 200 m from any nursery): "
                              f"NDVI {ix['ndvi']['adjacent_coef']:+.3f}, GNDVI {ix['gndvi']['adjacent_coef']:+.3f}, NDRE {ix['ndre']['adjacent_coef']:+.3f} "
                              f"(season and June value held constant; standard errors clustered by {CELL / 1000:.0f} km cell; p < 0.001 for each). "
                              f"The sign is the same in all three indices and in each of the three seasons; it survives soil covariates "
                              f"(NDRE {ix['ndre']['with_soil']['adjacent_coef']:+.3f} with K·S and plant-available water). The largest gap was in 2024 "
                              f"({ix['ndre']['per_season']['2024']['difference']:+.3f} NDRE), the smallest in 2025 ({ix['ndre']['per_season']['2025']['difference']:+.3f})."),
                   ("Flight distance", f"Fitting the decline as e^(−distance to the nearest nursery / r) with the same controls, the likelihood is highest "
                                       f"at r = {ix['ndre']['decay']['best_r_m']} m (profile band {ix['ndre']['decay']['r_band_m'][0]}–{ix['ndre']['decay']['r_band_m'][1]} m): "
                                       f"the effect is local: 50–100 m and 1 km or more fit clearly worse (the fit uses every declared beet parcel, "
                                       f"so the whole distance range is covered). The planner now defaults to 0.5 km and offers 0.25 / 0.5 / 1 km."),
                   ("What this is and is not", "This is an exposure–symptom association at landscape scale: nurseries nearby, more yellowing later. It is "
                                               "consistent with the rotation rule and with the vector's biology. It is not a measured SBR infection or sugar "
                                               "loss: drought and Cercospora also yellow beet, the \"control\" parcels are still within the adults' reach "
                                               "(which makes the difference smaller, not larger), and management is unobserved. Grower-level yield and sugar "
                                               "records would be needed to turn it into a damage estimate.")])

        # --- 2. data and method ----------------------------------------------------------------------------------
        text_page(pdf, "Data and method",
                  [("Parcels", "FIONA / InVeKoS declarations (LGL Baden-Württemberg, dl-de/by-2-0), application years 2022–2025, whole study bbox "
                               "(about 45 × 45 km, 114–127 thousand parcels a year). Sugar beet = NC 603; winter wheat = NC 112, 114, 115, 118, 156 "
                               "(soft and durum wheat, spelt, emmer/einkorn, triticale). A nursery is a wheat parcel of year t on ground that was "
                               "declared sugar beet in t−1 (parcel ids change between years; the match is the largest-overlap polygon). Per season: "
                               + "; ".join(f"{y}: {v.get('nursery_adjacent', 0):,} beet parcels next to a nursery, {v.get('control', 0):,} controls" for y, v in r["parcels"].items()) + "."),
                   ("Roles", "Nursery-adjacent: a beet parcel whose boundary is < 50 m from a nursery boundary. Control: < 50 m from control wheat "
                             "(wheat not after beet) and ≥ 200 m from any nursery. The adjacent-vs-control test uses these two groups; the decay "
                             "fit uses every declared beet parcel. Distances are boundary-to-boundary in EPSG:25832."),
                   ("Satellite data", "HLS S30 v2.0 (Harmonized Landsat Sentinel-2, NASA LP DAAC), 30 m, Sentinel-2 only (its red-edge band). Bands "
                                      "B04 (red), B8A (NIR), B05 (red edge 1), B03 (green) and Fmask. The granules were found with the CMR search and "
                                      "read as cloud-optimised GeoTIFFs over HTTPS for the window that covers the parcels; only parcel statistics "
                                      "were stored. Cloud, cloud shadow, adjacent and snow pixels masked with Fmask; granules with more than 70 % "
                                      "cloud skipped. " + "; ".join(f"{y}: {n} pictures" for y, n in r["pictures"].items()) + "."),
                   ("Indices", "NDVI = (NIR − red) / (NIR + red); GNDVI = (NIR − green) / (NIR + green); NDRE = (NIR − red edge) / (NIR + red edge). "
                               "NDRE saturates less over a closed canopy and reacts earlier to chlorosis, which is why it carries the headline. "
                               "A parcel's value is the mean over its pure 30 m pixels (pixel centre at least 15 m inside the outline, at least "
                               "4 such pixels, at least 60 % of them clear)."),
                   ("Windows", "June 1–25 (healthy, closing canopy) and August 15 – September 10 (peak SBR yellowing, before the beet lifting). "
                               "Each window is the mean of its clear pictures; a parcel-season needs at least two in each. The outcome is "
                               "delta = late-summer value − June value."),
                   ("Model", "One observation per parcel and season (no grid points: the pixels of one parcel share its value). "
                             "OLS: delta ~ nursery-adjacent + June value + season, then + K·S erosion factor + plant-available water (BK50 / "
                             "NASADEM, via the FIONA 2022 parcel under the centroid, matched for 99 %). Standard errors clustered by 2 km grid "
                             "cell (neighbouring parcels share weather and often a farm). Placebo: is the June level itself different next to a "
                             "nursery? Decay: delta ~ exp(−distance to the nearest nursery / r) + the same controls, with r profiled over "
                             f"{', '.join(str(x) for x in R_GRID)} m; the best r and the set within 2 log-likelihood units are reported."),
                   ("Reproduction", "prep/fetch_hls_region.py (about 35 minutes for three seasons), then pipeline/planthopper_region.py; "
                                    "results in data/processed/planthopper_effect/region_summary.json. All code in the Crop Circles repository.")])

        # --- 3. results table ------------------------------------------------------------------------------------
        rows = [("Index", "n", "Adjacent effect", "95 % CI", "p", "+ soil", "June placebo", "best r (band)")]
        for k, lab in LABEL.items():
            v = ix[k]
            ci = f"{v['adjacent_coef'] - 1.96 * v['adjacent_se']:+.3f} to {v['adjacent_coef'] + 1.96 * v['adjacent_se']:+.3f}"
            rows.append((lab, f"{v['n']:,}", f"{v['adjacent_coef']:+.4f}", ci, "< 0.001" if v["adjacent_p"] < 0.001 else f"{v['adjacent_p']:.3f}",
                         f"{v['with_soil']['adjacent_coef']:+.4f}", f"{v['placebo_june_level']['adjacent_coef']:+.4f} (p {v['placebo_june_level']['p']:.2f})",
                         f"{v['decay']['best_r_m']} m ({v['decay']['r_band_m'][0]}–{v['decay']['r_band_m'][1]})"))
        per = [("Season", "Index", "n adj. / ctrl", "June adj. / ctrl", "delta adj. / ctrl", "Difference", "Welch p")]
        for y in ("2023", "2024", "2025"):
            for k, lab in LABEL.items():
                v = ix[k]["per_season"][y]
                per.append((y, lab, f"{v['n_adjacent']} / {v['n_control']}", f"{v['june_adjacent']:.3f} / {v['june_control']:.3f}",
                            f"{v['mean_adjacent']:+.3f} / {v['mean_control']:+.3f}", f"{v['difference']:+.3f}",
                            "< 0.001" if v["welch_p"] < 0.001 else f"{v['welch_p']:.3f}"))
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.text(0.08, 0.95, "Results", fontsize=16, fontweight="bold", color=INK, va="top")
        fig.text(0.08, 0.915, "Table 1. Effect of lying next to a nursery on the June → late-summer change of each index\n"
                              "(OLS, season and June value held constant, 2 km-cluster SEs).", fontsize=9, color=GREY, va="top")
        ax = fig.add_axes([0.06, 0.70, 0.88, 0.19]); ax.axis("off")
        t1 = ax.table(cellText=rows[1:], colLabels=rows[0], loc="center", cellLoc="center")
        t1.auto_set_font_size(False); t1.set_fontsize(7.2); t1.scale(1, 1.5)
        fig.text(0.08, 0.66, "Table 2. The plain difference per season and index (adj. = next to a nursery, ctrl = control; mean delta,\n"
                             "Welch test, no covariates).", fontsize=9, color=GREY, va="top")
        ax = fig.add_axes([0.06, 0.30, 0.88, 0.34]); ax.axis("off")
        t2 = ax.table(cellText=per[1:], colLabels=per[0], loc="center", cellLoc="center")
        t2.auto_set_font_size(False); t2.set_fontsize(7.2); t2.scale(1, 1.45)
        for t in (t1, t2):
            for (i, j), c in t.get_celld().items():
                c.set_edgecolor("#dde2e8")
                if i == 0:
                    c.set_text_props(fontweight="bold", color=INK); c.set_facecolor("#f1f3f6")
        fig.text(0.08, 0.26, textwrap.fill(
            "Reading the tables: a delta of −0.05 NDRE between June and late summer is about a tenth of the June level "
            "(0.36–0.60 NDRE here; the June window catches the canopy while it is still closing, which is why 2023 rises further by late summer). The nursery-adjacent parcels start June slightly greener (placebo column, +0.01), so the "
            "difference is not a worse starting point; the June value is in the model to absorb the room to fall. The 2024 gap is the "
            "largest in every index; 2024 was also the season in which the Thünen crop map under-detected nurseries (2,378 ha against "
            "3,889 ha declared), which is why the declarations, not the map, define the roles here.", 98), fontsize=9, color=INK, va="top")
        pdf.savefig(fig); plt.close(fig)

        # --- 4. figure: delta by role and season --------------------------------------------------------------------
        fig, axes = plt.subplots(1, 3, figsize=(11.69, 5.2), sharey=True)
        for ax, (k, lab) in zip(axes, LABEL.items()):
            dd = d[k]
            pos, data, colors, ticks = [], [], [], []
            for i, y in enumerate((2023, 2024, 2025)):
                for j, (role, col) in enumerate((("control", GREY), ("nursery_adjacent", PINK))):
                    data.append(dd.delta[(dd.year == y) & (dd.role == role)].values); pos.append(i * 3 + j); colors.append(col)
                ticks.append(i * 3 + 0.5)
            bp = ax.boxplot(data, positions=pos, widths=0.8, patch_artist=True, showfliers=False, medianprops=dict(color="white", lw=1.5))
            for patch, col in zip(bp["boxes"], colors):
                patch.set_facecolor(col); patch.set_edgecolor(col)
            ax.axhline(0, color="#999999", lw=0.8)
            ax.set_xticks(ticks); ax.set_xticklabels(["2023", "2024", "2025"]); ax.set_title(lab); ax.grid(axis="y", alpha=0.3)
        axes[0].set_ylabel("late summer − June")
        fig.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=GREY), plt.Rectangle((0, 0), 1, 1, color=PINK)],
                   labels=["control: next to other winter wheat", "next to a nursery (wheat after beet)"], loc="lower center", ncol=2, frameon=False)
        fig.suptitle("Figure 1. Canopy change from June to late summer by season and neighbour (boxes: quartiles, line: median)", fontsize=10, color=INK)
        fig.tight_layout(rect=(0, 0.06, 1, 0.95)); pdf.savefig(fig); plt.close(fig)

        # --- 5. figure: coefficients and the decay profile --------------------------------------------------------
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.69, 5.0), gridspec_kw={"width_ratios": [1, 1.3]})
        labels, ys = [], []
        for i, (k, lab) in enumerate(LABEL.items()):
            v = ix[k]
            for j, (name, c, se) in enumerate((("season + June", v["adjacent_coef"], v["adjacent_se"]),
                                               ("+ soil (K·S, nFK)", v["with_soil"]["adjacent_coef"], v["with_soil"]["adjacent_se"]))):
                y = i * 2.6 + j
                a1.errorbar(c, y, xerr=1.96 * se, fmt="o", color=PINK if j == 0 else INK, capsize=3)
                labels.append(f"{lab} · {name}"); ys.append(y)
        a1.set_yticks(ys); a1.set_yticklabels(labels, fontsize=8); a1.axvline(0, color="#999999", lw=0.8); a1.invert_yaxis()
        a1.set_xlabel("effect of a nursery next door on the June → late-summer change (95 % CI)"); a1.grid(axis="x", alpha=0.3)
        a1.set_title("Figure 2a. The effect, with and without soil covariates")
        for k, lab, col in (("ndvi", "NDVI", GREY), ("gndvi", "GNDVI", POS), ("ndre", "NDRE", PINK)):
            prof = pd.DataFrame(ix[k]["decay"]["profile"])
            a2.plot(prof.r_m, prof.llf - prof.llf.max(), "o-", color=col, label=lab)
        a2.axhline(-2, color="#999999", lw=0.8, ls="--"); a2.text(R_GRID[-1], -2.2, "2 log-likelihood units", ha="right", va="top", fontsize=8, color=GREY)
        a2.set_xscale("log"); a2.set_xticks(R_GRID); a2.set_xticklabels([str(x) for x in R_GRID]); a2.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        a2.set_xlabel("flight distance r in e^(−distance / r), m"); a2.set_ylabel("log-likelihood relative to the best r")
        a2.set_title("Figure 2b. Which flight distance fits the decline best?"); a2.legend(frameon=False); a2.grid(alpha=0.3)
        fig.tight_layout(); pdf.savefig(fig); plt.close(fig)

        # --- 6. figure: decline against distance (binned) and the map ----------------------------------------------
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.69, 5.2), gridspec_kw={"width_ratios": [1, 1]})
        dd = d["ndre"].copy()
        dd["delta"] = dd.delta - dd.groupby("year").delta.transform("mean")  # season mean removed
        bins = [0, 25, 50, 100, 200, 400, 800, 1600, 3001]
        dd["bin"] = pd.cut(dd.dist_to_source, bins, right=False)
        g = dd.groupby("bin", observed=True).delta.agg(["mean", "sem", "size"])
        x = np.arange(len(g))
        a1.bar(x, g["mean"], yerr=1.96 * g["sem"], color=[PINK if i < 2 else GREY for i in x], capsize=3)
        a1.set_xticks(x); a1.set_xticklabels([f"{int(b.left)}–{int(b.right)}\nn = {n}" for b, n in zip(g.index, g["size"])], fontsize=7.5)
        a1.axhline(0, color="#999999", lw=0.8); a1.set_xlabel("distance to the nearest nursery boundary, m")
        a1.set_ylabel("NDRE, late summer − June, season mean removed (mean, 95 % CI)"); a1.set_title("Figure 3a. The decline by distance to a nursery"); a1.grid(axis="y", alpha=0.3)
        for role, col, lab in (("control", GREY, "control"), ("nursery_adjacent", PINK, "next to a nursery")):
            s = parcels[parcels.role == role]
            a2.scatter((s.x - parcels.x.min()) / 1000, (s.y - parcels.y.min()) / 1000, s=2, color=col, alpha=0.5, label=lab)
        a2.set_aspect("equal"); a2.set_xlabel("km east"); a2.set_ylabel("km north"); a2.legend(frameon=False, markerscale=4)
        a2.set_title("Figure 3b. The sampled beet parcels, 2023–2025"); a2.grid(alpha=0.3)
        fig.tight_layout(); pdf.savefig(fig); plt.close(fig)

        # --- 7. limitations ----------------------------------------------------------------------------------------
        text_page(pdf, "Limitations and next steps",
                  [("Not a diagnosis", "NDVI / NDRE decline is a symptom. SBR, Stolbur, Cercospora leaf spot, drought stress and early senescence all "
                                       "lower it. The association with nurseries is specific to the vector's biology, but no parcel in this sample "
                                       "has a laboratory result or a delivery record. Sugar content, where SBR does its economic damage, is not observed."),
                   ("Confounding", "Soil (K·S erosion factor, plant-available water) is now in the model and changes the estimate by less than "
                                   "10 %. Management, variety, sowing date, irrigation and the farm itself are not observed. A farm that puts "
                                   "wheat straight after beet may farm differently in other ways too."),
                   ("Spillover", "Adults fly; \"control\" parcels 200 m or more from a nursery are still exposed to some of them. The estimate "
                                 "is therefore the difference between heavy and lighter exposure, not between exposure and none, and is "
                                 "biased towards zero."),
                   ("Distance resolution", "The decay fit uses every declared beet parcel (adjacent, control and the ones in between) and r from "
                                           "50 m to 3 km, so both ends of the profile are resolved: 50–100 m and 1 km or more are clearly worse than "
                                           "250–500 m. The nearest nursery boundary is the only exposure measure; several nurseries around a parcel "
                                           "are not added up here (the planner does that)."),
                   ("Mean reversion", "Parcels that are greener in June have more to lose by late summer. The nursery-adjacent parcels start "
                                      "June slightly greener (+0.01), so the June value is in every model; a non-linear June term did not "
                                      "change the sign in a check."),
                   ("Cloud and timing", "A parcel-season needs two clear pictures in each window. 2024 had the fewest June pictures (6 "
                                        "granules) and the fewest parcel-seasons (814). Late summer ends on 10 September, before the beet "
                                        "lifting; a parcel lifted early would still show as a decline."),
                   ("Next", "1. Relax the parcel filter to every beet parcel and fit the decay on the full distance range. 2. Ask Südzucker / "
                            "the SBR task force for delivery data (sugar content) of a sample of these parcels. 3. Repeat with ECOSTRESS "
                            "evaporative stress as the outcome to separate water stress from disease. 4. Use the fitted flight distance "
                            "(250–500 m) is now the planner's default (0.5 km, slider 0.25 / 0.5 / 1 km).")],
                  subtitle="Crop Circles · region-wide planthopper edge test")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
