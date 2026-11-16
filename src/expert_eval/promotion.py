"""Promotion evaluation: can any dynamic / restricted-six-expert blend beat the incumbent?

The incumbent is the site's current static three-expert weights (config.STATIC_WEIGHTS) -- that is
the primary benchmark and the only thing the promotion gate is measured against. Equal weighting
(3 and 6 experts) is a secondary benchmark, reported but not gating.

Strategies are fixed in advance (no tuning on results):
  static3        incumbent
  equal3/equal6  secondary benchmarks
  dyn3 / dyn6    the shadow Kalman weights, used as-is (reference)
  anchorNN       incumbent x (1-NN%) + the three extra experts (Harmon, Pianowski, Winks) equal-split x NN%
                 -- NN in {10, 20, 30}: a dose-response read on whether the extras add information
  plus_<x>       incumbent x 85% + one extra expert x 15% (which extra, if any, helps)
  anchor20dyn    CANDIDATE: incumbent x 80% + extras x 20%, the extras split by their learned (shadow) weights
  blend50        CANDIDATE: 50% shadow six-expert weights + 50% incumbent (shrunk toward the incumbent)
Only the two CANDIDATES are eligible for promotion; the rest are diagnostics (so the multiple-comparison
exposure is two candidates, not a search).

All strategies are weighted rank averages on the site's rank scales, scored on identical frozen pools and
seeded scenarios. Weights for week t use only weeks < t. Weeks are the unit of evidence."""
import itertools
import json
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.expert_eval import evaluate as E
from src.expert_eval.audit import WeekCache
from src.expert_eval.backtest import blend_ranks, bootstrap, load_frozen, static_weights, weekly_edges
from src.expert_eval.config import CONFIG_VERSION, CORE_THREE, SCORINGS, SOURCES, SPEC
from src.expert_eval.weights import run_filter

EXTRAS = [s for s in SOURCES if s not in CORE_THREE]
CANDIDATES = ["anchor20dyn", "blend50"]


def _norm(d: dict) -> dict:
    t = sum(d.values())
    return {s: (v / t if t > 0 else 0.0) for s, v in d.items()}


def _mix(parts) -> "callable":
    """parts: [(coef, fn(pos)->dict)] -> fn(pos)->normalized dict."""
    def f(pos):
        out = {s: 0.0 for s in SOURCES}
        for c, fn in parts:
            for s, v in fn(pos).items():
                out[s] += c * v
        return _norm(out)
    return f


def _const(d: dict):
    n = _norm(d)
    return lambda pos: n


def build_strategies(dyn6: pd.Series | None, dyn3: pd.Series | None, present: list) -> dict:
    """name -> fn(pos)->weights, for one week. `present`: sources that published this week."""
    pres = [s for s in SOURCES if s in present]
    ex = [s for s in EXTRAS if s in pres]
    core = [s for s in CORE_THREE if s in pres]
    static = lambda pos: _norm({s: w for s, w in static_weights(pos).items() if s in pres})
    S = {"static3": static,
         "equal3": _const({s: 1.0 for s in core}),
         "equal6": _const({s: 1.0 for s in pres})}
    if dyn3 is not None:
        S["dyn3"] = _const({s: float(dyn3.get(s, 0)) for s in core})
    if dyn6 is not None:
        d6 = {s: float(dyn6.get(s, 0)) for s in pres}
        S["dyn6"] = _const(d6)
        S["blend50"] = _mix([(0.5, _const(d6)), (0.5, static)])
        if ex:
            S["anchor20dyn"] = _mix([(0.8, static), (0.2, _const({s: d6[s] for s in ex}))])
    if ex:
        for m in (10, 20, 30):
            S[f"anchor{m}"] = _mix([(1 - m / 100, static), (m / 100, _const({s: 1.0 for s in ex}))])
        for s in ex:
            S[f"plus_{s}"] = _mix([(0.85, static), (0.15, _const({s: 1.0}))])
    return S


def _regret(cache: WeekCache, w: int, fn) -> float:
    c = cache.weeks[w]
    zero = lambda pos: {s: (v if s in c["present"] else 0.0) for s, v in fn(pos).items()}
    r = blend_ranks(c["raw"], c["imp"], zero, c["pos"])
    return float(c["sc"].regret({"x": r}, c["pts"])["x"]["total"].mean())


def _dyn_tables(edges: pd.DataFrame) -> tuple:
    six = run_filter(edges, SOURCES, "x", "six")
    from src.expert_eval.pipeline import renormalize_subset
    three = renormalize_subset(run_filter(edges, SOURCES, "x", "three"), CORE_THREE)
    f = lambda df: {k[1]: g.set_index("source").weight for k, g in df.groupby(["season", "week"])}
    return f(six), f(three)


def weekly_panel(cache: WeekCache, edges: pd.DataFrame, weeks, dyn6_override=None) -> tuple:
    """strategy -> {week: regret}, plus effective default-position weights per week (for turnover)."""
    six, three = _dyn_tables(edges)
    reg, eff = {}, {}
    for w in weeks:
        d6 = dyn6_override[w] if dyn6_override is not None else six.get(w)
        S = build_strategies(d6, three.get(w), cache.weeks[w]["present"])
        for name, fn in S.items():
            reg.setdefault(name, {})[w] = _regret(cache, w, fn)
            eff.setdefault(name, {})[w] = pd.Series(fn("WR"))
    return reg, eff


def _turnover(eff: dict, weeks) -> float:
    ws = [eff[w] for w in weeks if w in eff]
    d = [0.5 * (b - a.reindex(b.index).fillna(0)).abs().sum() for a, b in zip(ws[:-1], ws[1:])]
    return float(np.mean(d)) if d else 0.0


def permutation_p(cache: WeekCache, edges: pd.DataFrame, weeks, name: str) -> dict:
    """Exact test: give the learned skill estimates to every possible relabeling of the six experts and ask how
    often that does as well (saved vs the incumbent) as the real assignment. Needs a dynamic component."""
    six, _ = _dyn_tables(edges)
    base = {w: _regret(cache, w, build_strategies(None, None, cache.weeks[w]["present"])["static3"]) for w in weeks}

    def saved(d6map):
        vals = []
        for w in weeks:
            fn = build_strategies(d6map[w], None, cache.weeks[w]["present"])[name]
            vals.append(base[w] - _regret(cache, w, fn))
        return float(np.mean(vals))

    actual = saved({w: six[w] for w in weeks})
    null = []
    for perm in itertools.permutations(range(len(SOURCES))):
        names = [SOURCES[i] for i in perm]
        null.append(saved({w: pd.Series({SOURCES[j]: six[w][names[j]] for j in range(len(SOURCES))}) for w in weeks}))
    null = np.array(null)
    return {"actual": actual, "null_mean": float(null.mean()), "null_p95": float(np.percentile(null, 95)),
            "p_value": float((null >= actual - 1e-12).mean())}


def gate(stats: dict, turnover: float | None, perm_p: float | None) -> dict:
    g = SPEC["gate"]
    checks = {"improvement": stats["mean"] >= g["min_improvement"], "p_improve": stats["p_improve"] >= g["min_p_improve"],
              "weeks_worse": stats["share_weeks_worse"] <= g["max_share_weeks_worse"],
              "worst_week": stats["worst_week"] >= -g["max_worst_week_deficit"],
              "turnover": turnover is None or turnover <= g["max_avg_turnover"]}
    if perm_p is not None:
        checks["permutation"] = perm_p <= g["max_perm_p"]
    return {"checks": checks, "pass": all(checks.values())}


def run_promotion(store, season: int, config_version: str = CONFIG_VERSION, provenance: str = "pipeline",
                  log=print, first_week: int = 2, permutation: bool = True, save: bool = True,
                  scorings=SCORINGS) -> dict:
    frozen = {sc: load_frozen(store, season, sc, config_version, provenance) for sc in scorings}
    edges_all = weekly_edges(frozen, season, scorings)
    report = {"season": season, "config_version": config_version, "provenance": provenance, "benchmark": "static3", "scorings": {}}
    for scoring in scorings:
        snap, res, pools = frozen[scoring]
        edges = edges_all[scoring]
        cache = WeekCache(season, scoring, snap, res, pools)
        weeks = [w for w in sorted(cache.weeks) if w >= first_week]
        reg, eff = weekly_panel(cache, edges, weeks)
        df = pd.DataFrame(reg).sort_index()
        out = {"weeks": weeks, "mean_regret": df.mean().round(3).to_dict(), "comparisons": {}}
        for name in df.columns:
            if name in ("static3",):
                continue
            for base in ("static3", "equal6" if name != "equal6" else "equal3"):
                if base not in df.columns:
                    continue
                d = (df[base] - df[name]).dropna().values
                st = bootstrap(d)
                tv = _turnover(eff[name], weeks) if (name.startswith("dyn") or name in CANDIDATES) else None
                pp, g = None, None
                if base == "static3" and name in CANDIDATES:
                    g = gate(st, tv, None)
                    # the (slow) exact permutation test only runs for a candidate that cleared every other check
                    if permutation and g["pass"]:
                        pp = permutation_p(cache, edges, weeks, name)["p_value"]
                        g = gate(st, tv, pp)
                out["comparisons"][f"{name}_vs_{base}"] = {**st, "turnover": tv, "perm_p": pp, "gate": g, "candidate": name in CANDIDATES}
        report["scorings"][scoring] = out
        log(f"[{scoring}] weeks {weeks[0]}-{weeks[-1]} ({len(weeks)} wks), regret static3 {df.static3.mean():.2f}")
        for k, v in out["comparisons"].items():
            if k.endswith("_vs_static3"):
                gt = "" if v["gate"] is None else (" GATE PASS" if v["gate"]["pass"] else " gate fail: " + ",".join(c for c, ok in v["gate"]["checks"].items() if not ok))
                pp = "" if v["perm_p"] is None else f" perm_p={v['perm_p']:.3f}"
                log(f"  {k:26s} {v['mean']:+.2f} pts/wk [{v['lo']:+.2f},{v['hi']:+.2f}] P>0={v['p_improve']:.2f} weeks worse {v['share_weeks_worse']:.2f} worst {v['worst_week']:+.1f}{pp}{gt}")
        for k in ("dyn6_vs_equal6", "static3_vs_equal6"):
            pass
    report["both_formats_pass"] = {n: all(report["scorings"][sc]["comparisons"].get(f"{n}_vs_static3", {}).get("gate", {}) and
                                          report["scorings"][sc]["comparisons"][f"{n}_vs_static3"]["gate"]["pass"] for sc in scorings)
                                   for n in CANDIDATES}
    log("candidate passes in BOTH formats:", report["both_formats_pass"])
    if save:
        run_id = f"promo-{config_version}-{season}-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:4]
        for sc in scorings:
            store.upsert("expert_eval_backtests", [{
                "run_id": f"{run_id}-{sc}", "config_version": config_version, "scoring": sc,
                "summary": {**report["scorings"][sc], "both_formats_pass": report["both_formats_pass"], "benchmark": "static3",
                            "provenance": provenance, "season": season}, "weekly": None}])
        report["run_id"] = run_id
    return report
