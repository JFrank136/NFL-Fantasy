"""Shadow weighting engine.

Per expert, a local-level Kalman filter tracks true skill = mean weekly *edge* (field-average
lineup regret minus own regret, points/week). Observations are weeks; an absent expert gets no
update (its uncertainty grows). Skill shrinks toward 0 (= the field) with a prior spread and
a per-week drift, plus a larger variance bump at each new season so old evidence fades without
being discarded. Posterior skill -> softmax tilt on top of equal weights -> floor/cap ->
rate limit. Weights for week t use only weeks < t.

Nothing here touches the live site; weights are written to expert_eval_weights (shadow)."""
from dataclasses import dataclass, field
from math import erf, sqrt

import numpy as np
import pandas as pd

from src.expert_eval.config import SPEC, CONFIG_VERSION


@dataclass
class SkillState:
    m: float = 0.0
    P: float = 0.0
    n_obs: int = 0
    total: float = 0.0     # sum of observed edges (for the raw mean)


def estimate_sigma2(history: list, cfg=None) -> float:
    """Pooled weekly-edge noise variance from observations so far (as-of), else the default."""
    cfg = cfg or SPEC["weights"]
    vals = [row.dropna() for row in history]
    n_weeks = len(vals)
    if n_weeks < cfg["sigma_min_weeks"]:
        return cfg["sigma_default"] ** 2
    df = pd.DataFrame(history)
    v = df.var(ddof=1)
    v = v[df.count() >= 3]
    return float(v.mean()) if len(v) else cfg["sigma_default"] ** 2


def bounded_normalize(w: np.ndarray, lo, hi) -> np.ndarray:
    """Scale w to sum to 1 while keeping each entry inside [lo, hi] (per-entry arrays ok):
    pin violators at their bound and rescale the free entries, repeating until stable."""
    k = len(w)
    lo, hi = np.broadcast_to(np.asarray(lo, float), k), np.broadcast_to(np.asarray(hi, float), k)
    w = np.asarray(w, float) / np.sum(w)
    if lo.sum() > 1 + 1e-9 or hi.sum() < 1 - 1e-9:        # infeasible bounds: fall back to a plain clip
        c = np.clip(w, lo, hi)
        return c / c.sum()
    out, fixed = w.copy(), np.zeros(k, bool)
    for _ in range(k + 2):
        free = ~fixed
        rem = 1 - out[fixed].sum()
        out[free] = w[free] / w[free].sum() * rem
        over, under = free & (out > hi + 1e-12), free & (out < lo - 1e-12)
        if not over.any() and not under.any():
            break
        out[over], out[under] = hi[over], lo[under]
        fixed |= over | under
    return out


def clip_normalize(w: np.ndarray, floor: float, cap: float) -> tuple[np.ndarray, list]:
    """Weights bounded to [floor, cap] x equal share. Returns (weights, reason codes)."""
    k = len(w)
    w0 = np.asarray(w, float) / np.sum(w)
    out = bounded_normalize(w0, floor / k, cap / k)
    reasons = ["capped" if out[i] >= cap / k - 1e-9 and w0[i] > out[i] else
               "floored" if out[i] <= floor / k + 1e-9 and w0[i] < out[i] else "" for i in range(k)]
    return out, reasons


def softmax_weights(skill: pd.Series, prev: pd.Series | None, cfg=None):
    """equal-share tilt by exp(beta*skill), bounded, then rate-limited vs last week's weights."""
    cfg = cfg or SPEC["weights"]
    k = len(skill)
    w, reasons = clip_normalize(np.exp(cfg["beta"] * skill.values), cfg["floor"], cfg["cap"])
    if prev is not None:
        step = cfg["max_step"] / k
        p = prev.reindex(skill.index).fillna(1 / k).values
        lo = np.maximum(cfg["floor"] / k, p - step)
        hi = np.minimum(cfg["cap"] / k, p + step)
        lim = bounded_normalize(w, lo, hi)
        for i in range(k):
            if abs(lim[i] - w[i]) > 1e-9:
                reasons[i] = "rate_limited"
        w = lim
    return pd.Series(w, index=skill.index), pd.Series(reasons, index=skill.index)


def p_better(m: float, sd: float) -> float:
    return 0.5 * (1 + erf(m / (sd * sqrt(2)))) if sd > 0 else 0.5


def run_filter(edges: pd.DataFrame, sources: list, scoring: str, weight_set: str,
               cfg=None, config_version: str = CONFIG_VERSION) -> pd.DataFrame:
    """edges: index = MultiIndex (season, week) ascending, columns = sources (NaN = absent that week).
    Returns one row per (season, week, source) = the weights that would apply TO that week,
    computed from strictly earlier weeks."""
    cfg = cfg or SPEC["weights"]
    cols = [s for s in sources if s in edges.columns] or list(sources)
    edges = edges.reindex(columns=cols)
    states = {s: SkillState(P=cfg["tau0"] ** 2) for s in cols}
    history, prev_w, prev_season = [], None, None
    out = []
    for (season, week), obs in edges.iterrows():
        # predict step for this week's target (season boundary adds extra variance)
        if prev_season is not None and season != prev_season:
            for st in states.values():
                st.P += cfg["q_season"]
        prev_season = season
        skill = pd.Series({s: states[s].m for s in cols})
        sd = pd.Series({s: sqrt(states[s].P) for s in cols})
        w, reason = softmax_weights(skill, prev_w, cfg)
        k = len(cols)
        for s in cols:
            st = states[s]
            r = reason[s] or ("prior_only" if st.n_obs == 0 else "tilt")
            out.append(dict(
                season=season, week=week, scoring=scoring, weight_set=weight_set, source=s,
                position="ALL", tier="ALL", config_version=config_version,
                weight=float(w[s]), equal_weight=1 / k, skill_mean=st.m, skill_sd=sd[s],
                p_better=p_better(st.m, sd[s]), weeks_n=st.n_obs,
                raw_mean=(st.total / st.n_obs) if st.n_obs else None, reason=r))
        prev_w = w
        # observe week's edges, then roll the filter forward
        sigma2 = estimate_sigma2(history, cfg)
        for s in cols:
            st = states[s]
            st.P += cfg["q"]
            y = obs.get(s)
            if y is not None and y == y:
                gain = st.P / (st.P + sigma2)
                st.m += gain * (y - st.m)
                st.P *= (1 - gain)
                st.n_obs += 1
                st.total += y
        history.append(obs)
    return pd.DataFrame(out)
