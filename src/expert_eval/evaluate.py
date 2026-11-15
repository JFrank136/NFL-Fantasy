"""One week of evaluation for one scoring format: frozen pool, seeded roster
scenarios, lineup regret (primary), plus pairwise / rank-correlation diagnostics
sliced by position and consensus tier.

Everything is on the site's own rank scales (QB; FLEX = RB/WR/TE), so FLEX-slot
choices use each expert's native cross-position ordering and no rank->points
curve (and so no future-data leakage risk) is needed in v1."""
import hashlib

import numpy as np
import pandas as pd

from src.expert_eval.config import SPEC, SCORING_COL
from src.expert_eval.names import scale_group

POS = ("QB", "RB", "WR", "TE")
COMPS = ["total", "QB", "RB", "WR", "TE", "FLEX"]


def week_seed(season: int, week: int, scoring: str) -> int:
    h = hashlib.sha256(f"{season}-{week}-{scoring}-{SPEC['seed_salt']}".encode()).hexdigest()
    return int(h[:8], 16)


def attach_results(cands: pd.DataFrame, results_week: pd.DataFrame, scoring: str) -> pd.DataFrame:
    """Adds pts + inactive to (canon, position) candidates. Match on name+position first,
    then name alone among offensive positions (e.g. a FB listed RB by one side, TE by the
    other). Unmatched players are scored 0 and counted, not silently dropped."""
    col = SCORING_COL[scoring]
    res = results_week[["canon", "position", col, "inactive"]].rename(columns={col: "pts", "position": "rpos"})
    out = cands.merge(res, left_on=["canon", "position"], right_on=["canon", "rpos"], how="left")
    miss = out.pts.isna()
    if miss.any():
        byname = res.drop_duplicates("canon").set_index("canon")
        out.loc[miss, "pts"] = out.loc[miss, "canon"].map(byname.pts)
        out.loc[miss, "inactive"] = out.loc[miss, "canon"].map(byname.inactive)
    out["matched"] = out.pts.notna()
    out["pts"] = out.pts.fillna(0.0)
    out["inactive"] = out.inactive.fillna(False).astype(bool)
    return out.drop(columns="rpos")


def build_pool(snap: pd.DataFrame, results_week: pd.DataFrame, scoring: str):
    """Expert-neutral pool: top-N per position by equal-weight mean scaled rank across all
    sources present, minus confirmed-inactive players. Returns (pool, count of pool players with no result row)."""
    cand = snap.groupby(["canon", "position"], as_index=False).scaled_rank.mean().rename(columns={"scaled_rank": "consensus"})
    cand = attach_results(cand, results_week, scoring)
    cand = cand[~cand.inactive]
    parts = []
    for pos in POS:
        c = cand[cand.position == pos].sort_values(["consensus", "canon"]).head(SPEC["pool_size"][pos]).copy()
        c["pos_rank"] = np.arange(1, len(c) + 1)
        parts.append(c)
    pool = pd.concat(parts, ignore_index=True)
    return pool, int((~pool.matched).sum())   # pool players with no result row (scored 0, flagged)


def rank_matrix(snap: pd.DataFrame, pool: pd.DataFrame, sources):
    """pool x source scaled ranks; unranked imputed at that source's max rank in the group + 1.
    Also returns per-source coverage (share of pool actually ranked)."""
    piv = snap.pivot_table(index=["canon", "position"], columns="source", values="scaled_rank", aggfunc="first")
    idx = pd.MultiIndex.from_frame(pool[["canon", "position"]])
    m = piv.reindex(idx).reindex(columns=list(sources))
    cov = m.notna().mean()
    grp = pool.position.map(scale_group).values
    sgrp = snap.position.map(scale_group)
    for s in m.columns:
        for g in ("QB", "FLEX"):
            mask = grp == g
            mx = snap[(snap.source == s) & (sgrp == g)].scaled_rank.max()
            m.loc[mask, s] = m.loc[mask, s].fillna((mx if mx == mx else 0) + 1)
    m.index = pool.index
    return m, cov


class Scenarios:
    """Seeded roster draws shared by every expert/strategy for a (season, week, scoring)."""

    def __init__(self, pool: pd.DataFrame, seed: int, n: int | None = None):
        self.n = n or SPEC["n_scenarios"]
        rng = np.random.default_rng(seed)
        self.idx = {}
        for pos in POS:
            members = np.flatnonzero((pool.position == pos).values)
            k = min(SPEC["roster"][pos], len(members))
            order = rng.random((self.n, len(members))).argsort(axis=1)[:, :k]
            self.idx[pos] = members[order]            # (n, k) pool row positions

    def regret(self, ranks: dict, pts: np.ndarray) -> dict:
        """ranks: name -> array over pool rows (lower = better). Returns name -> {component: (n,) regret}."""
        opt = self._lineup(-pts, pts)
        out = {}
        for name, r in ranks.items():
            got = self._lineup(np.asarray(r, float), pts)
            comp = {c: opt[c] - got[c] for c in POS}
            comp["total"] = opt["total"] - got["total"]
            comp["FLEX"] = comp["total"] - sum(comp[c] for c in POS)
            out[name] = comp
        return out

    def _lineup(self, rank: np.ndarray, pts: np.ndarray) -> dict:
        res, left_r, left_p = {}, [], []
        for pos in POS:
            ix = self.idx[pos]
            r, p = rank[ix], pts[ix]
            o = np.argsort(r, axis=1, kind="stable")
            ps = np.take_along_axis(p, o, axis=1)
            rs = np.take_along_axis(r, o, axis=1)
            k = SPEC["starters"][pos]
            res[pos] = ps[:, :k].sum(axis=1)
            if pos != "QB":
                left_r.append(rs[:, k:])
                left_p.append(ps[:, k:])
        lr, lp = np.concatenate(left_r, axis=1), np.concatenate(left_p, axis=1)
        res["FLEX"] = lp[np.arange(self.n), lr.argmin(axis=1)]
        res["total"] = res["QB"] + res["RB"] + res["WR"] + res["TE"] + res["FLEX"]
        return res


def pair_diagnostics(pool: pd.DataFrame, ranks: dict) -> list:
    """Pairwise start/sit accuracy + points captured for same-position pairs close in
    consensus rank, sliced by position and by the consensus tier of the better-ranked
    player in the pair; plus rank correlation with points per position. Pool players only."""
    rows = []
    gap, tiers = SPEC["pair_gap"], SPEC["tiers"]
    pts_all = pool.pts.values
    for pos in POS:
        sel = np.flatnonzero((pool.position == pos).values)
        if len(sel) < 6:
            continue
        pr, pt = pool.pos_rank.values[sel], pts_all[sel]
        I, J = np.triu_indices(len(sel), 1)
        m = (np.abs(pr[I] - pr[J]) <= gap) & (pt[I] != pt[J])
        I, J = I[m], J[m]
        win, dp, top = pt[I] > pt[J], np.abs(pt[I] - pt[J]), np.minimum(pr[I], pr[J])
        for name, r in ranks.items():
            rr = np.asarray(r, float)[sel]
            ok = rr[I] != rr[J]
            right = (rr[I] < rr[J]) == win
            for tier, (lo, hi) in [("ALL", (0, 10**6))] + list(tiers.items()):
                t = ok & (top >= lo) & (top <= hi)
                n = int(t.sum())
                if n == 0:
                    continue
                d = dp[t]
                rows.append(dict(source=name, position=pos, tier=tier, metric="pair_acc", value=float(right[t].mean()), n=n))
                rows.append(dict(source=name, position=pos, tier=tier, metric="pair_pts",
                                 value=float(np.where(right[t], d, -d).sum() / d.sum()), n=n))
            if pt.std() > 0 and rr.std() > 0:
                rho = pd.Series(-rr).rank().corr(pd.Series(pt).rank())
                rows.append(dict(source=name, position=pos, tier="ALL", metric="rank_corr", value=float(rho), n=len(sel)))
    df = pd.DataFrame(rows)
    if len(df):
        for (src, tier, metric), g in df.groupby(["source", "tier", "metric"]):
            w = g.n if metric != "rank_corr" else None
            rows.append(dict(source=src, position="ALL", tier=tier, metric=metric,
                             value=float(np.average(g.value, weights=w)), n=int(g.n.sum())))
    return rows


def evaluate_week(season: int, week: int, scoring: str, snap: pd.DataFrame, results_week: pd.DataFrame,
                  pool=None, extra_ranks=None):
    """Returns (score_rows, pool, info). `pool` may be a stored (frozen) pool; `extra_ranks`
    (name -> array over pool rows) scores synthetic blends on the identical scenarios."""
    snap = snap[(snap.week == week) & (snap.scoring == scoring)]
    if snap.empty:
        return [], None, {"reason": "no snapshots"}
    unmatched = 0
    if pool is None:
        pool, unmatched = build_pool(snap, results_week, scoring)
    else:
        pool = attach_results(pool[["canon", "position", "consensus", "pos_rank"]].copy(), results_week, scoring)
        unmatched = int((~pool.matched).sum())
    pool = pool.reset_index(drop=True)
    sources = sorted(snap.source.unique())
    rm, cov = rank_matrix(snap, pool, sources)
    present = [s for s in sources if cov[s] >= SPEC["min_coverage"]]
    ranks = {s: rm[s].values for s in present}
    if extra_ranks:
        ranks.update(extra_ranks)
    sc = Scenarios(pool, week_seed(season, week, scoring))
    reg = sc.regret(ranks, pool.pts.values)
    field = {c: np.mean([reg[s][c].mean() for s in present]) for c in COMPS} if present else {}
    rows = []
    for name, comp in reg.items():
        for c in COMPS:
            pos = "ALL" if c == "total" else c
            rows.append(dict(source=name, position=pos, tier="ALL", metric="regret", value=float(comp[c].mean()), n=sc.n))
            if name in present:
                rows.append(dict(source=name, position=pos, tier="ALL", metric="edge_regret",
                                 value=float(field[c] - comp[c].mean()), n=sc.n))
    rows += pair_diagnostics(pool, ranks)
    for s in sources:
        rows.append(dict(source=s, position="ALL", tier="ALL", metric="coverage", value=float(cov[s]), n=len(pool)))
        rows.append(dict(source=s, position="ALL", tier="ALL", metric="n_imputed", value=float((1 - cov[s]) * len(pool)), n=len(pool)))
    rows.append(dict(source="field", position="ALL", tier="ALL", metric="field_size", value=float(len(present)), n=len(present)))
    rows.append(dict(source="field", position="ALL", tier="ALL", metric="pool_unmatched", value=float(unmatched), n=len(pool)))
    info = {"present": present, "absent": [s for s in sources if s not in present], "pool": len(pool), "unmatched": unmatched}
    return rows, pool, info
