"""Walk-forward backtest: would dynamic weights have beaten equal / static weights?

For each week t the weights come from the Kalman filter fed only weeks < t (no curve is
fit in v1, so nothing else can leak). Every strategy is a weighted rank average on the
site's rank scales and is scored on the identical frozen pool and seeded roster scenarios.
Weeks are the independent observations: intervals are week-bootstrap, never scenario-based."""
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.expert_eval import evaluate as E
from src.expert_eval.config import CONFIG_VERSION, CORE_THREE, SCORINGS, SOURCES, SPEC, STATIC_WEIGHTS, SCORING_COL
from src.expert_eval.pipeline import pool_from_db, renormalize_subset, results_from_db, snaps_from_db
from src.expert_eval.weights import run_filter


def raw_rank_matrix(snap: pd.DataFrame, pool: pd.DataFrame, sources) -> pd.DataFrame:
    piv = snap.pivot_table(index=["canon", "position"], columns="source", values="scaled_rank", aggfunc="first")
    m = piv.reindex(pd.MultiIndex.from_frame(pool[["canon", "position"]])).reindex(columns=list(sources))
    m.index = pool.index
    return m


def blend_ranks(raw: pd.DataFrame, imputed: pd.DataFrame, weights, positions: pd.Series) -> np.ndarray:
    """Weighted average rank, a missing source's weight redistributed over the sources that
    ranked the player (mirrors site weightedAverageRank). `weights` is a dict source->w or a
    callable position->dict. Players nobody ranked fall back to the imputed mean."""
    out = np.empty(len(raw))
    for pos, idx in positions.groupby(positions).groups.items():
        w = weights(pos) if callable(weights) else weights
        cols = [c for c in raw.columns if w.get(c, 0) > 0]
        vals = raw.loc[idx, cols].values.astype(float)
        wv = np.array([w[c] for c in cols])[None, :] * ~np.isnan(vals)
        tot = wv.sum(axis=1)
        score = np.where(tot > 0, np.nansum(vals * wv, axis=1) / np.where(tot > 0, tot, 1), np.nan)
        fall = imputed.loc[idx, cols].mean(axis=1).values if cols else np.zeros(len(idx))
        out[raw.index.get_indexer(idx)] = np.where(np.isnan(score), fall, score)
    return out


def static_weights(pos: str) -> dict:
    w = STATIC_WEIGHTS.get(pos, STATIC_WEIGHTS["default"])
    return {s: w.get(s, 0.0) for s in SOURCES}


def load_frozen(store, season: int, scoring: str, config_version: str = CONFIG_VERSION, provenance: str = "pipeline"):
    snap = snaps_from_db(store.select("expert_eval_snapshots", season=season, scoring=scoring, provenance=provenance))
    res = results_from_db(store.select("expert_eval_results", season=season))
    weeks = sorted(snap.week.unique())
    pools = {w: pool_from_db(store.select("expert_eval_pool", season=season, week=int(w), scoring=scoring, config_version=config_version)) for w in weeks}
    return snap, res, pools


def weekly_edges(frozen: dict, season: int, scorings=SCORINGS) -> dict:
    """scoring -> DataFrame (season,week) x source of overall regret edges, from the frozen inputs."""
    out = {}
    for scoring in scorings:
        snap, res, pools = frozen[scoring]
        rows = {}
        for w in sorted(pools):
            r, _, info = E.evaluate_week(season, int(w), scoring, snap, res[res.week == w], pool=pools[w])
            for x in r:
                if x["metric"] == "edge_regret" and x["position"] == "ALL":
                    rows.setdefault((season, int(w)), {})[x["source"]] = x["value"]
        out[scoring] = pd.DataFrame.from_dict(rows, orient="index").sort_index().reindex(columns=SOURCES)
        out[scoring].index = pd.MultiIndex.from_tuples(out[scoring].index, names=["season", "week"])
    return out


def pooled(edges: dict) -> pd.DataFrame:
    a, b = edges[SCORINGS[0]], edges[SCORINGS[1]]
    return pd.concat([a, b]).groupby(level=[0, 1]).mean().sort_index()


def weight_tables(edges: dict) -> dict:
    """(scoring, variant) -> {'six': {(season, week): Series}, 'three': ...}; variant 'sep' or 'pool'."""
    res = {}
    for scoring in SCORINGS:
        for variant, e in (("sep", edges[scoring]), ("pool", pooled(edges))):
            six = run_filter(e, SOURCES, scoring, "six")
            three = renormalize_subset(run_filter(e, SOURCES, scoring, "three"), CORE_THREE)
            res[(scoring, variant)] = {
                name: {k: g.set_index("source").weight for k, g in df.groupby(["season", "week"])}
                for name, df in (("six", six), ("three", three))}
    return res


def strategy_ranks(season, w, snap, pool, wt, scoring):
    snap_w = snap[(snap.week == w) & (snap.scoring == scoring)]
    rm_imp, cov = E.rank_matrix(snap_w, pool, SOURCES)
    raw = raw_rank_matrix(snap_w, pool, SOURCES)
    present6 = [s for s in SOURCES if cov.get(s, 0) >= SPEC["min_coverage"]]
    present3 = [s for s in CORE_THREE if s in present6]
    pos = pool.position
    ranks = {}

    def eq(members):
        d = {s: 1.0 for s in members}
        return {s: d.get(s, 0.0) for s in SOURCES}

    ranks["equal6"] = blend_ranks(raw, rm_imp, eq(present6), pos)
    ranks["equal3"] = blend_ranks(raw, rm_imp, eq(present3), pos)
    ranks["static3"] = blend_ranks(raw, rm_imp, static_weights, pos)
    for variant, tag in (("sep", ""), ("pool", "p")):
        tbl = wt[(scoring, variant)]
        for name, members in (("6", present6), ("3", present3)):
            wser = tbl["six" if name == "6" else "three"].get((season, w))
            if wser is None:
                continue
            d = {s: float(wser.get(s, 0.0)) if s in members else 0.0 for s in SOURCES}
            ranks[f"dyn{name}{tag}"] = blend_ranks(raw, rm_imp, d, pos)
    for s in present6:
        ranks[f"indiv_{s}"] = rm_imp[s].values
    return ranks, present6


def bootstrap(diffs: np.ndarray, B: int = 5000, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    n = len(diffs)
    means = np.array([rng.choice(diffs, n, replace=True).mean() for _ in range(B)])
    return {"mean": float(diffs.mean()), "lo": float(np.percentile(means, 10)), "hi": float(np.percentile(means, 90)),
            "p_improve": float((means > 0).mean()), "share_weeks_worse": float((diffs < 0).mean()),
            "worst_week": float(diffs.min()), "n_weeks": n}


COMPARISONS = [("dyn6", "equal6"), ("dyn6p", "equal6"), ("dyn3", "equal3"), ("dyn3p", "equal3"),
               ("dyn3", "static3"), ("dyn6", "static3"), ("equal6", "equal3"), ("equal6", "static3"), ("equal3", "static3")]


def gate_verdict(stats: dict, turnover: float | None, perm_p: float | None = None) -> dict:
    g = SPEC["gate"]
    checks = {
        "improvement": stats["mean"] >= g["min_improvement"],
        "p_improve": stats["p_improve"] >= g["min_p_improve"],
        "weeks_worse": stats["share_weeks_worse"] <= g["max_share_weeks_worse"],
        "worst_week": stats["worst_week"] >= -g["max_worst_week_deficit"],
        "turnover": turnover is None or turnover <= g["max_avg_turnover"],
    }
    if perm_p is not None:
        checks["permutation"] = perm_p <= g["max_perm_p"]
    return {"checks": checks, "pass": all(checks.values())}


def turnover(tbl: dict, key: str, weeks: list) -> float:
    ws = [tbl[key][w] for w in weeks if w in tbl[key]]
    d = [0.5 * (b - a.reindex(b.index)).abs().sum() for a, b in zip(ws[:-1], ws[1:])]
    return float(np.mean(d)) if d else 0.0


def backtest(store, season: int, log=print, first_week: int = 2, permutation: bool = True) -> dict:
    from src.expert_eval.audit import WeekCache, permutation_test
    frozen = {sc: load_frozen(store, season, sc) for sc in SCORINGS}
    edges = weekly_edges(frozen, season)
    wt = weight_tables(edges)
    summary, weekly = {}, {}
    for scoring in SCORINGS:
        snap, res, pools = frozen[scoring]
        reg = {}
        for w in sorted(pools):
            ranks, present = strategy_ranks(season, int(w), snap, pools[w], wt, scoring)
            sc = E.Scenarios(pools[w].reset_index(drop=True), E.week_seed(season, int(w), scoring))
            pool = E.attach_results(pools[w][["canon", "position", "consensus", "pos_rank"]].copy(), res[res.week == w], scoring).reset_index(drop=True)
            r = sc.regret(ranks, pool.pts.values)
            reg[int(w)] = {k: float(v["total"].mean()) for k, v in r.items()}
        df = pd.DataFrame(reg).T.sort_index()
        weekly[scoring] = df
        use = df[df.index >= first_week]
        perm = permutation_test(WeekCache(season, scoring, snap, res, pools), edges[scoring], first_week) if permutation else None
        s = {"mean_regret": use.mean().round(3).to_dict(), "weeks": [int(x) for x in use.index], "comparisons": {}}
        for a, b in COMPARISONS:
            if a in use and b in use:
                d = (use[b] - use[a]).dropna().values            # points saved by a relative to b
                st = bootstrap(d)
                tv = None
                if a.startswith("dyn"):
                    variant = "pool" if a.endswith("p") else "sep"
                    tv = turnover(wt[(scoring, variant)], "six" if a[3] == "6" else "three",
                                  [(season, int(w)) for w in use.index])
                pp = perm["p_value"] if (perm and a == "dyn6" and b == "equal6") else None
                s["comparisons"][f"{a}_vs_{b}"] = {**st, "turnover": tv, "perm_p": pp,
                                                   "gate": gate_verdict(st, tv, pp) if a.startswith("dyn") else None}
        s["permutation"] = perm
        s["indiv_vs_equal6"] = {c: bootstrap((use["equal6"] - use[c]).values) for c in use.columns if c.startswith("indiv_")}
        summary[scoring] = s
        log(f"[{scoring}] weeks {s['weeks'][0]}-{s['weeks'][-1]}")
        for k, v in s["comparisons"].items():
            gt = "" if not v["gate"] else (" GATE PASS" if v["gate"]["pass"] else " gate fail " + ",".join(c for c, ok in v["gate"]["checks"].items() if not ok))
            if v.get("perm_p") is not None:
                gt += f"  perm_p={v['perm_p']:.3f}"
            log(f"  {k:22s} saved {v['mean']:+.2f} pts/wk  [{v['lo']:+.2f},{v['hi']:+.2f}]  P>0={v['p_improve']:.2f}  weeks worse {v['share_weeks_worse']:.2f}  worst {v['worst_week']:+.1f}{gt}")
    run_id = "bt-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:4]
    for scoring in SCORINGS:
        store.upsert("expert_eval_backtests", [{
            "run_id": f"{run_id}-{scoring}", "config_version": CONFIG_VERSION, "scoring": scoring,
            "summary": summary[scoring], "weekly": weekly[scoring].round(4).reset_index().rename(columns={"index": "week"}).to_dict("records")}])
    return {"summary": summary, "weekly": weekly, "run_id": run_id}
