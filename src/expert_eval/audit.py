"""Audit of the walk-forward backtest (does the dynamic-weights gain survive scrutiny?).

Checks, all on the stored (frozen) evidence:
  1. leakage      weights for week t are unchanged when every week >= t is replaced with garbage
  2. permutation  re-assign the learned skills to random experts (all 720 relabelings of six):
                  how often does a weights path unrelated to the truth do as well as the real one?
  3. outliers     leave-one-week-out gain, median week, and gain with the filter itself refit
                  without that week
  4. policy       how much the inactive-player policy moves the edges (none / known_early / all_confirmed)
Weeks are the unit; scenarios are shared across strategies."""
import itertools
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.expert_eval import evaluate as E
from src.expert_eval.backtest import (blend_ranks, load_frozen, raw_rank_matrix, weekly_edges)
from src.expert_eval.config import CONFIG_VERSION, SCORINGS, SOURCES, SPEC
from src.expert_eval.store import EXPORT_DIR
from src.expert_eval.weights import run_filter


class WeekCache:
    """Per-week objects reused across thousands of strategy evaluations."""

    def __init__(self, season, scoring, snap, res, pools):
        self.weeks = {}
        for w in sorted(pools):
            w = int(w)
            pool = E.attach_results(pools[w][["canon", "position", "consensus", "pos_rank"]].copy(), res[res.week == w], scoring).reset_index(drop=True)
            sn = snap[(snap.week == w) & (snap.scoring == scoring)]
            imp, cov = E.rank_matrix(sn, pool, SOURCES)
            present = [s for s in SOURCES if cov.get(s, 0) >= SPEC["min_coverage"]]
            self.weeks[w] = dict(pool=pool, pts=pool.pts.values, imp=imp, raw=raw_rank_matrix(sn, pool, SOURCES), present=present,
                                 sc=E.Scenarios(pool, E.week_seed(season, w, scoring)), pos=pool.position)

    def regret(self, w, weights: dict) -> float:
        c = self.weeks[w]
        d = {s: float(weights.get(s, 0.0)) if s in c["present"] else 0.0 for s in SOURCES}
        r = blend_ranks(c["raw"], c["imp"], d, c["pos"])
        return float(c["sc"].regret({"x": r}, c["pts"])["x"]["total"].mean())

    def equal(self, w) -> float:
        return self.regret(w, {s: 1.0 for s in self.weeks[w]["present"]})


def _weights_by_week(edges: pd.DataFrame) -> dict:
    out = run_filter(edges, SOURCES, "x", "six")
    return {k[1]: g.set_index("source").weight for k, g in out.groupby(["season", "week"])}


def saved_per_week(cache: WeekCache, wts: dict, weeks) -> pd.Series:
    return pd.Series({w: cache.equal(w) - cache.regret(w, wts[w]) for w in weeks if w in wts})


def check_leakage(edges: pd.DataFrame, seed=0) -> dict:
    rng = np.random.default_rng(seed)
    base = _weights_by_week(edges)
    worst, checked = 0.0, 0
    for t in list(edges.index)[1:]:
        e2 = edges.copy()
        later = [i for i in e2.index if i >= t]
        e2.loc[later] = rng.normal(0, 5, (len(later), e2.shape[1]))
        alt = _weights_by_week(e2)
        d = (base[t[1]] - alt[t[1]]).abs().max()
        worst = max(worst, float(d)); checked += 1
    return {"weeks_checked": checked, "max_weight_difference": worst, "passes": worst < 1e-12}


def permutation_test(cache: WeekCache, edges: pd.DataFrame, first_week=2) -> dict:
    base = _weights_by_week(edges)
    weeks = [w for w in base if w >= first_week and w in cache.weeks]
    actual = saved_per_week(cache, base, weeks).mean()
    null = []
    for perm in itertools.permutations(range(len(SOURCES))):
        names = [SOURCES[i] for i in perm]
        mapped = {w: pd.Series({SOURCES[j]: base[w][names[j]] for j in range(len(SOURCES))}) for w in weeks}
        null.append(saved_per_week(cache, mapped, weeks).mean())
    null = np.array(null)
    return {"actual_saved": float(actual), "null_mean": float(null.mean()), "null_sd": float(null.std()),
            "null_p95": float(np.percentile(null, 95)), "p_value": float((null >= actual - 1e-12).mean()), "n_labelings": len(null)}


def outlier_check(cache: WeekCache, edges: pd.DataFrame, first_week=2) -> dict:
    base = _weights_by_week(edges)
    weeks = [w for w in base if w >= first_week and w in cache.weeks]
    s = saved_per_week(cache, base, weeks)
    res = {"per_week": {int(k): round(float(v), 3) for k, v in s.items()}, "mean": float(s.mean()), "median": float(s.median()),
           "leave_one_out_mean": {}, "refit_without_week_mean": {}}
    for w in weeks:
        res["leave_one_out_mean"][int(w)] = float(s.drop(w).mean())
        e2 = edges.drop([i for i in edges.index if i[1] == w])
        wb = _weights_by_week(e2)
        keep = [x for x in weeks if x != w and x in wb]
        res["refit_without_week_mean"][int(w)] = float(saved_per_week(cache, wb, keep).mean())
    res["min_leave_one_out"] = min(res["leave_one_out_mean"].values())
    res["min_refit_without_week"] = min(res["refit_without_week_mean"].values())
    res["gain_share_top_week"] = float(s.max() / s.clip(lower=0).sum()) if s.clip(lower=0).sum() > 0 else None
    return res


def policy_check(store, season, scoring) -> dict:
    """Edge by expert under each inactive policy, using stored snapshots/results (pools rebuilt per policy)."""
    snap, res, _ = load_frozen(store, season, scoring)
    out = {}
    old = SPEC["inactive_policy"]
    try:
        for pol in ("none", "known_early", "all_confirmed"):
            SPEC["inactive_policy"] = pol
            rows = []
            for w in sorted(snap.week.unique()):
                r, _, _ = E.evaluate_week(season, int(w), scoring, snap, res[res.week == w])
                rows += [(int(w), x["source"], x["value"]) for x in r if x["metric"] == "edge_regret" and x["position"] == "ALL"]
            d = pd.DataFrame(rows, columns=["w", "s", "v"]).pivot_table(index="w", columns="s", values="v")
            out[pol] = d[d.index >= 2].mean().round(3).to_dict()
    finally:
        SPEC["inactive_policy"] = old
    t = pd.DataFrame(out)
    out["spearman_vs_all_confirmed"] = {p: float(t[p].corr(t["all_confirmed"], method="spearman")) for p in ("none", "known_early")}
    return out


def audit(store, season: int, log=print) -> dict:
    report = {"config_version": CONFIG_VERSION, "season": season, "run_at": datetime.now(timezone.utc).isoformat(), "scorings": {}}
    frozen = {sc: load_frozen(store, season, sc) for sc in SCORINGS}
    edges_all = weekly_edges(frozen, season)
    for scoring in SCORINGS:
        snap, res, pools = frozen[scoring]
        cache = WeekCache(season, scoring, snap, res, pools)
        edges = edges_all[scoring]
        r = {"leakage": check_leakage(edges), "permutation": permutation_test(cache, edges),
             "outliers": outlier_check(cache, edges), "inactive_policy": policy_check(store, season, scoring)}
        report["scorings"][scoring] = r
        log(f"[{scoring}] leakage {r['leakage']}")
        log(f"[{scoring}] permutation {r['permutation']}")
        o = r["outliers"]
        log(f"[{scoring}] outliers mean {o['mean']:+.3f} median {o['median']:+.3f} min leave-one-out {o['min_leave_one_out']:+.3f} "
            f"min refit-without {o['min_refit_without_week']:+.3f} per-week {o['per_week']}")
        log(f"[{scoring}] inactive policy {json.dumps(r['inactive_policy'])}")
    path = EXPORT_DIR / f"audit_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(report, indent=2, default=float), encoding="utf-8")
    log(f"audit written to {path}")
    return report


# ---- integrity: format separation + history preservation --------------------------------------

_VOLATILE = {"calc_at", "data_as_of", "created_at", "started_at"}


def table_fingerprint(store, table: str, **eq) -> dict:
    """order-independent content hash per natural-key group, ignoring timestamps."""
    import hashlib
    df = store.select(table, **eq)
    if df.empty:
        return {}
    df = df[[c for c in df.columns if c not in _VOLATILE]].astype(str)
    return {"rows": len(df), "hash": hashlib.sha256(df.sort_values(list(df.columns)).to_csv(index=False).encode()).hexdigest()[:16]}


def verify_integrity(store, season: int, rerun=None, log=print) -> dict:
    """1) the two scoring formats never share evidence: stored weights equal a filter fed only that
    format's own edges; 2) a full rerun leaves frozen snapshots, pools, history of older config
    versions and (absent stat corrections) results and scores byte-identical."""
    from src.expert_eval.pipeline import load_edges
    out = {"separation": {}, "preservation": {}}
    for scoring in SCORINGS:
        e = load_edges(store, scoring)
        w = store.select("expert_eval_weights", scoring=scoring, config_version=CONFIG_VERSION, weight_set="six")
        mine = run_filter(e.reindex(columns=SOURCES), SOURCES, scoring, "six").set_index(["season", "week", "source"]).weight
        stored = w.set_index(["season", "week", "source"]).weight
        j = pd.concat([mine, stored], axis=1, keys=["mine", "stored"]).dropna()
        out["separation"][scoring] = {"weights_match_own_edges_only": bool((j.mine - j.stored).abs().max() < 1e-9), "rows": len(j)}
    h, p = (e for e in (load_edges(store, s) for s in SCORINGS))
    common = h.index.intersection(p.index)
    out["separation"]["formats_not_copies"] = bool((h.loc[common] - p.loc[common]).abs().stack().max() > 0.01)
    tables = [("expert_eval_snapshots", {"season": season}), ("expert_eval_pool", {"season": season, "config_version": CONFIG_VERSION}),
              ("expert_eval_results", {"season": season}), ("expert_eval_scores", {"season": season, "config_version": CONFIG_VERSION})]
    older = store.select("expert_eval_scores", season=season, config_version="v1")
    before = {t: table_fingerprint(store, t, **kw) for t, kw in tables}
    older_before = len(older)
    if rerun:
        rerun()
    after = {t: table_fingerprint(store, t, **kw) for t, kw in tables}
    out["preservation"] = {t: {"unchanged": before[t] == after[t], **after[t]} for t, _ in tables}
    out["preservation"]["older_config_rows_kept"] = {"v1_score_rows_before": older_before,
                                                      "v1_score_rows_after": len(store.select("expert_eval_scores", season=season, config_version="v1"))}
    log(json.dumps(out, indent=1))
    return out
