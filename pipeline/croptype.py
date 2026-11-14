"""What grows on a parcel, as probabilities: winter cereal, sugar beet or something else, from how green it is month by
month. Used by hls.py; numpy and pandas only.

The model is a multinomial logistic regression with an L2 penalty (Newton steps, halved while they do not lower the
loss) on the monthly median NDVI February–October, the NDVI of the November–December before (cover crop or bare) and
last year's crop (the rotation: beet is rarely followed by beet, often by winter wheat). It learns seven groups and adds
the last five up to "other", so beet gets its own boundary against maize, potato and spring barley instead of a single
one against everything else. GNDVI and NDRE join as monthly medians once they are downloaded, but only if they make
the year-by-year test below better.

Labels: the farmer's FIONA declaration where there is one (2022 on), else the Thünen crop map (2019 on; 2025
preliminary). Both are opinions with their own errors, the map more than the declaration.

How it is tested: each labelled year is predicted by a model fitted on the other years only (leave one year out), so
the weather of the year being tested is new to the model, as it is for the running season. Those out-of-sample
predictions make every check number. The penalty was picked with the same test: 0.003 and 0.01 tie (log loss 0.267
and 0.270 on NDVI, 2019–2025), 0.03 is worse (0.307); the stronger of the two is kept.
A feature a parcel lacks (clouds, a season still running, NDRE only from Sentinel-2) is not guessed: the model for
that parcel is refitted on the training parcels that have the features it has.
"""
import numpy as np
import pandas as pd

LAMBDA = 0.01
MONTHS = range(2, 11)            # February–October; January and November are too often cloudy (half the parcel-years)
PREV = ["prev_winter", "prev_beet", "prev_other"]   # last year's crop, one-hot; all 0 = unknown
WINTER, BEET = {1101, 1102, 1103}, 1402            # Thünen: winter wheat, barley, rye; sugar beet
# the "other" groups: maize; spring cereals; potato, vegetables, peas, beans, lupin, soy; rapeseed; 6 = the rest
# (grassland, vines, orchards, set-aside, sunflower, ...)
GROUP = {1300: 2, 1201: 3, 1202: 3, 1401: 4, 1603: 4, 1611: 4, 1612: 4, 1613: 4, 1614: 4, 1501: 5}
K = 7
DECLARED_WINTER = r"(?i)winter.*(?:weizen|gerste|roggen|dinkel|emmer|triticale|hafer)"  # FIONA names of winter cereals
DECLARED_BEET = "Zuckerrüben"
CONFIDENCE_BINS = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]


def softmax(z):
    e = np.exp(z - z.max(1, keepdims=True))
    return e / e.sum(1, keepdims=True)


def fit(X, y, k, lam=LAMBDA):
    """Multinomial logistic regression on standardised X (n x m) with labels 0..k-1; returns the predict function.
    The intercepts get almost no penalty."""
    mu, sd = X.mean(0), X.std(0)
    sd = np.where(sd > 1e-6, sd, 1.0)  # a column constant in training (e.g. no beet last year) stays at weight 0
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]
    n, m = Z.shape
    Y, W, pen = np.eye(k)[y], np.zeros((m, k)), np.r_[1e-4, np.full(m - 1, lam)][:, None]
    loss = lambda W: -np.sum(Y * np.log(softmax(Z @ W) + 1e-300)) / n + 0.5 * np.sum(pen * W ** 2)
    for _ in range(100):
        P = softmax(Z @ W)
        g = Z.T @ (P - Y) / n + pen * W
        H = np.einsum("ia,ib,ikl->akbl", Z, Z, P[:, :, None] * np.eye(k) - P[:, :, None] * P[:, None, :]) / n
        step = np.linalg.solve(H.reshape(m * k, m * k) + np.diag(np.repeat(pen.ravel(), k)), g.ravel()).reshape(m, k)
        t, before = 1.0, loss(W)
        while loss(W - t * step) > before and t > 1e-4:
            t /= 2
        W -= t * step
        if np.abs(t * step).max() < 1e-7:
            break
    return lambda X2: softmax(np.c_[np.ones(len(X2)), (X2 - mu) / sd] @ W)


def group(declared, crop):
    """0 winter cereal, 1 sugar beet, 2-6 the other groups, -1 no label. FIONA first; for its "other" the Thünen code
    tells which other group."""
    other = np.array([GROUP.get(c, 6) for c in crop])
    thuenen = np.select([crop.isin(WINTER), crop == BEET, crop > 0], [0, 1, other], -1)
    fiona = np.select([declared.str.contains(DECLARED_WINTER, na=False), declared.str.contains(DECLARED_BEET, na=False),
                       declared.notna()], [0, 1, other], -1)
    return np.where(fiona >= 0, fiona, thuenen)


def columns(indices):
    return [f"{i}_{m:02d}" for i in indices for m in MONTHS] + ["cover"]


def predict(train, test, cols):
    """P(winter cereal, sugar beet, other) per test row (n x 3), from models fitted on `train`, one per pattern of the
    features the test rows have."""
    p = np.zeros((len(test), K))
    for have, idx in test[cols].notna().groupby(cols).groups.items():
        use = [c for c, h in zip(cols, have) if h] + PREV
        tr = train.dropna(subset=use)
        seen = np.unique(tr.group)
        p[test.index.get_indexer(idx)[:, None], seen] = fit(tr[use].to_numpy(float), np.searchsorted(seen, tr.group),
                                                            len(seen))(test.loc[idx, use].to_numpy(float))
    return np.c_[p[:, 0], p[:, 1], p[:, 2:].sum(1)]


def out_of_sample(lab, cols):
    p = np.zeros((len(lab), 3))
    for y in lab.year.unique():
        test = (lab.year == y).to_numpy()
        p[test] = predict(lab[~test], lab[test], cols)
    return p


def log_loss(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-15, 1))))


def brier(p, y):
    return float(np.mean(((np.eye(3)[y] - p) ** 2).sum(1)))


def wilson(k, n, z=1.96):
    """95 % interval of a share k/n (Wilson score; sound for 17 of 17, unlike k/n ± 2 SE)."""
    if not n:
        return [0.0, 1.0]
    c, h = (k + z * z / 2) / (n + z * z), z * np.sqrt(k * (n - k) / n + z * z / 4) / (n + z * z)
    return [round(max(c - h, 0), 3), round(min(c + h, 1), 3)]


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def year_sd(p, hit, years):
    """How far a year's weather moves all parcels at once, as an SD on the log-odds scale. Per held-out year the miss
    D = seen - expected count is about V * shift plus counting noise of variance V = sum p(1-p), so over the years
    SD² = sum(D² - V) / sum(V²) (method of moments; 0 when the misses are no bigger than chance)."""
    d = pd.DataFrame({"y": years, "D": hit - p, "V": p * (1 - p)}).groupby("y").sum()
    return round(float(np.sqrt(max((d.D ** 2 - d.V).sum(), 0) / (d.V ** 2).sum())), 3)


def spread(p, ha, sd, draws=10_000):
    """How many of these parcels, and how many ha, are what each is with probability p: expected value and 90 % range
    from random draws. Each draw first shifts all parcels' log-odds together by N(0, sd) (a year that fools the model
    fools it on many parcels at once), then draws every parcel."""
    p, ha, rng = np.asarray(p, float), np.asarray(ha, float), np.random.default_rng(0)
    q = 1 / (1 + np.exp(-(logit(p) + rng.normal(0, sd, (draws, 1)))))
    hit = rng.random((draws, len(p))) < q
    n, a = hit.sum(1), hit @ ha
    return {"expected_n": round(float(p.sum()), 1), "expected_ha": round(float(p @ ha), 1),
            "range_n": np.percentile(n, [5, 95]).round().astype(int).tolist(),
            "range_ha": np.percentile(a, [5, 95]).round(1).tolist()}


def run(py):
    """Adds group, last year's crop, p_winter / p_beet / p_other and the most likely answer (winter, beet) to the
    parcel-years (one row per parcel and year, with the monthly medians, cover, declared, crop, crop_before).
    Labelled years get their leave-one-year-out prediction; the others (the running season) the model of all
    labelled years. Returns the frame and the test summary."""
    py = py.reset_index(drop=True)
    py["group"] = group(py.declared, py.crop)
    py["prev"] = py.merge(py[["id", "year", "group"]].assign(year=py.year + 1), on=["id", "year"], how="left",
                          suffixes=("", "_y")).group_y.to_numpy()
    first = py.prev.isna()  # the first year: last year's crop from the Thünen map alone
    py.loc[first, "prev"] = group(pd.Series(np.nan, index=py.index[first], dtype=object), py.crop_before[first])
    for k, c in enumerate(PREV):
        py[c] = (np.minimum(py.prev, 2) == k).astype(float)  # groups 2-6 are "other"
    sets = {"ndvi": columns(["ndvi"])}
    if py.filter(regex=r"^(gndvi|ndre)_\d\d$").notna().to_numpy().any():
        sets["ndvi+gndvi+ndre"] = columns(["ndvi", "gndvi", "ndre"])
    py = py.reindex(columns=list(dict.fromkeys([*py.columns, *sets.get("ndvi+gndvi+ndre", sets["ndvi"])])))
    lab = py[py.group >= 0]
    y3 = np.minimum(lab.group.to_numpy(), 2)  # 0 winter, 1 beet, 2 other
    tried = {name: out_of_sample(lab, cols) for name, cols in sets.items()}
    best = min(tried, key=lambda s: log_loss(tried[s], y3))
    p = np.zeros((len(py), 3))
    p[lab.index] = tried[best]
    rest = py.index[py.group < 0]
    if len(rest):
        p[rest] = predict(lab, py.loc[rest], sets[best])
    py["p_winter"], py["p_beet"], py["p_other"] = p.T
    py["winter"], py["beet"] = p.argmax(1) == 0, p.argmax(1) == 1

    q = tried[best]
    said, right = q.max(1), q.argmax(1) == y3
    rule = np.select([lab.rule_winter.eq(True), lab.rule_beet.eq(True)], [0, 1], 2)
    years = f"{lab.year.min()}-{lab.year.max()}"
    bins = pd.cut(said, [0, *CONFIDENCE_BINS], include_lowest=True)
    summary = {
        "method": "multinomial logistic regression, L2, leave-one-year-out test", "lambda": LAMBDA, "indices": best,
        "features": sets[best] + PREV, "years": years, "n": len(lab),
        "right": int(right.sum()), "accuracy": round(float(right.mean()), 3), "accuracy_95": wilson(right.sum(), len(lab)),
        "said": round(float(said.mean()), 3), "log_loss": round(log_loss(q, y3), 3), "brier": round(brier(q, y3), 3),
        "log_loss_by_indices": {s: round(log_loss(v, y3), 3) for s, v in tried.items()},
        "by_year": {int(y): round(float(right[(lab.year == y).to_numpy()].mean()), 3) for y in sorted(lab.year.unique())},
        "reliability": [{"bin": str(b), "n": int(len(g)), "said": round(float(g.said.mean()), 3),
                         "right": round(float(g.right.mean()), 3)}
                        for b, g in pd.DataFrame({"said": said, "right": right}).groupby(bins, observed=True)],
        "confusion": pd.crosstab(pd.Series(y3, name="true"), pd.Series(q.argmax(1), name="said"))
                       .reindex(index=range(3), columns=range(3), fill_value=0).to_numpy().tolist(),
        "classes": ["winter cereal", "sugar beet", "other"],
        "year_sd": {"winter": year_sd(q[:, 0], y3 == 0, lab.year.to_numpy()),
                    "beet": year_sd(q[:, 1], y3 == 1, lab.year.to_numpy())},
        "expected_by_year": {int(y): {"beet": round(float(q[t, 1].sum()), 1), "beet_seen": int((y3[t] == 1).sum()),
                                      "winter": round(float(q[t, 0].sum()), 1), "winter_seen": int((y3[t] == 0).sum())}
                             for y in sorted(lab.year.unique()) for t in [(lab.year == y).to_numpy()]},
        "rule": {"accuracy": round(float((rule == y3).mean()), 3), "accuracy_95": wilson((rule == y3).sum(), len(lab)),
                 "brier": round(brier(np.eye(3)[rule], y3), 3), "note": "thresholds tuned on these years (in-sample)"}}
    return py, summary
