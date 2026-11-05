"""Reed-planthopper pressure between parcels (numpy only, shared by the pipeline and the app).

A season y pairs the "nurseries" – winter wheat in y on parcels that grew sugar beet in y-1, where the nymphs
overwinter – with the beet parcels of y, which the adults reach in June (LIZ, SBR und Stolbur erklärt, Teil 2).
Pressure on a beet parcel = sum over nurseries of nursery ha × exp(-distance / r). r, the mean flight distance of
the adults, is not in our sources: it is a user setting (0.5–2 km), and results are shown for each value.
The sum is linear, so the pressure removed by switching one nursery is its own "impact".
"""
import numpy as np


def kernel(src_xy, dst_xy, r):
    """exp(-d/r) between every source and destination point (metres, EPSG:3035)."""
    d = np.hypot(src_xy[:, None, 0] - dst_xy[None, :, 0], src_xy[:, None, 1] - dst_xy[None, :, 1])
    return np.exp(-d / r, dtype=np.float32)


def impacts(nur_xy, nur_ha, beet_xy, beet_ha, r, chunk=1000):
    """(impact of each nursery on all beet area, pressure on each beet parcel); chunked to keep memory < ~150 MB."""
    imp, pres = np.empty(len(nur_xy), np.float32), np.zeros(len(beet_xy), np.float32)
    for i in range(0, len(nur_xy), chunk):
        k = kernel(nur_xy[i:i + chunk], beet_xy, r)
        imp[i:i + chunk] = nur_ha[i:i + chunk] * (k @ beet_ha)
        pres += nur_ha[i:i + chunk] @ k
    return imp, pres


def removed_curve(impact, area, order):
    """Share of pressure removed when nurseries are switched in `order`, against the share of nursery area switched."""
    return np.cumsum(area[order]) / area.sum(), np.cumsum(impact[order]) / impact.sum()


if __name__ == "__main__":  # self-check: a nursery next to the beet matters more than a far one
    nur, beet = np.array([[0.0, 0.0], [5000.0, 0.0]], np.float32), np.array([[100.0, 0.0]], np.float32)
    imp, p = impacts(nur, np.array([1.0, 1.0], np.float32), beet, np.array([2.0], np.float32), 1000)
    assert imp[0] > 100 * imp[1] and abs(p[0] - (np.exp(-0.1) + np.exp(-4.9))) < 1e-5
    x, y = removed_curve(imp, np.array([1.0, 1.0]), np.argsort(-imp))
    assert x[0] == 0.5 and y[0] > 0.99
    print("pressure.py ok")
