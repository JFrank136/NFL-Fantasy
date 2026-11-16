"""Weekly run: freeze snapshots + results, evaluate each finalized week, refresh shadow weights.

Idempotent: every write is an upsert on a natural key, and evaluation is deterministic
(seeded scenarios, frozen pool), so rerunning a week with the same inputs changes nothing.
A rerun after nflverse stat corrections updates that week's results/scores in place."""
import hashlib
import json
import uuid
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.expert_eval import evaluate as E, inputs, snapshots, results as results_mod
from src.expert_eval.config import CONFIG_VERSION, REALWORLD_VERSION, SCORINGS, SOURCES, CORE_THREE, SPEC, config_hash
from src.expert_eval.store import Store
from src.expert_eval.weights import run_filter

# ---- DB <-> in-memory column names -------------------------------------------------


def snaps_to_db(snap: pd.DataFrame, season: int) -> pd.DataFrame:
    d = snap.rename(columns={"canon": "canonical_name"}).copy()
    d["season"] = season
    return d[["season", "week", "source", "scoring", "canonical_name", "position", "raw_rank",
              "scaled_rank", "pulled_at", "kickoff_at", "provenance"]]


def snaps_from_db(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={"canonical_name": "canon"})


def results_to_db(res: pd.DataFrame, season: int) -> pd.DataFrame:
    d = res.rename(columns={"canon": "canonical_name"}).copy()
    d["season"] = season
    d["data_as_of"] = datetime.now(timezone.utc).isoformat()
    return d[["season", "week", "canonical_name", "position", "team", "played", "inactive", "status",
              "roster_status", "report_status", "pts_std", "pts_half", "pts_ppr", "data_as_of"]]


def results_from_db(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={"canonical_name": "canon"})


def pool_to_db(pool: pd.DataFrame, season: int, week: int, scoring: str, config_version: str = CONFIG_VERSION) -> pd.DataFrame:
    d = pool.rename(columns={"canon": "canonical_name", "consensus": "consensus_rank"}).copy()
    d["season"], d["week"], d["scoring"], d["config_version"] = season, week, scoring, config_version
    return d[["season", "week", "scoring", "canonical_name", "position", "consensus_rank", "config_version"]]


def pool_from_db(df: pd.DataFrame) -> pd.DataFrame:
    d = df.rename(columns={"canonical_name": "canon", "consensus_rank": "consensus"}).copy()
    # Must reproduce build_pool's row order exactly (scenario draws index into it): POS order,
    # then consensus, then name as the total-order tie-break.
    d["_p"] = d.position.map({p: i for i, p in enumerate(E.POS)})
    d = d.sort_values(["_p", "consensus", "canon"]).reset_index(drop=True)
    d["pos_rank"] = d.groupby("position").cumcount() + 1
    return d[["canon", "position", "consensus", "pos_rank"]]


def hash_rows(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.sort_index(axis=1).to_csv(index=False).encode()).hexdigest()[:16]


# ---- main entry --------------------------------------------------------------------


STATUS_PATH = BASE_STATUS = None  # set below (kept out of import-time side effects)
RECHECK_WEEKS = 2   # re-evaluate the latest N finalized weeks every run (nflverse stat corrections)


def _status_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent / "data" / "last_expert_eval_status.json"


def _write_status(payload: dict) -> None:
    p = _status_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _result_changes(old: pd.DataFrame, new: pd.DataFrame) -> int:
    """Rows whose stored points/status differ from the freshly built results (stat corrections)."""
    if old.empty:
        return 0
    k = ["season", "week", "canonical_name", "position"]
    m = old.merge(new, on=k, suffixes=("_o", "_n"))
    diff = (m.pts_ppr_o - m.pts_ppr_n).abs().fillna(0) > 0.01
    diff |= (m.pts_std_o - m.pts_std_n).abs().fillna(0) > 0.01
    diff |= m.status_o.fillna("") != m.status_n.fillna("")
    return int(diff.sum())


def run(season: int, weeks=None, store: Store | None = None, now=None, log=print, full: bool = False) -> dict:
    store = store or Store()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]
    started = datetime.now(timezone.utc).isoformat()
    try:
        out = _run(season, weeks, store, now, log, run_id, full)
        _write_status({"run_at": started, "ok": True, "run_id": run_id, "season": season, "config_version": CONFIG_VERSION, **out})
        return out
    except Exception as e:   # always leave a failure record the status email can report
        _write_status({"run_at": started, "ok": False, "run_id": run_id, "season": season, "error": f"{type(e).__name__}: {e}"})
        raise


def _run(season, weeks, store, now, log, run_id, full) -> dict:
    sched = inputs.load_schedule(season)
    final_weeks = [int(w) for w in sorted(sched.week.unique()) if inputs.week_is_final(sched, w, now)]
    if weeks:
        todo = [w for w in weeks if w in final_weeks]
    else:
        done = set(store.select("expert_eval_pool", season=season, config_version=CONFIG_VERSION).get("week", pd.Series(dtype=int)).astype(int))
        todo = [w for w in final_weeks if full or w not in done or w in final_weeks[-RECHECK_WEEKS:]]
    skipped = [w for w in (weeks or []) if w not in final_weeks]
    if not todo:
        log(f"No finalized weeks to evaluate (requested={weeks}, finalized={final_weeks}).")
        return {"weeks": [], "skipped": skipped, "result_changes": 0, "info": {}}

    store.upsert("expert_eval_config", [{"version": CONFIG_VERSION, "spec": SPEC}])
    # Snapshots are frozen evidence: weeks already stored are reused as-is, never reselected.
    stored = store.select("expert_eval_snapshots", season=season, provenance="pipeline")
    have = set(stored.week.astype(int)) if len(stored) else set()
    new_weeks = [w for w in todo if w not in have]
    parts = [snaps_from_db(stored[stored.week.isin(todo)])] if len(stored) else []
    if new_weeks:
        rankings = inputs.load_rankings(season, weeks=new_weeks)
        fresh = snapshots.select_snapshots(rankings, sched, SPEC["max_snapshot_age_days"])
        store.insert_missing("expert_eval_snapshots", snaps_to_db(fresh, season))
        parts.append(fresh)
    snap_all = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    res_all = results_mod.build_results(season)
    res_db = results_to_db(res_all[res_all.week.isin(todo)], season)
    old = store.select("expert_eval_results", season=season)
    changes = _result_changes(old[old.week.isin(todo)] if len(old) else old, res_db)
    store.upsert("expert_eval_results", res_db)
    log(f"weeks {todo} (new snapshots: {new_weeks}); stored results changed by corrections: {changes}")

    summary = {}
    for scoring in SCORINGS:
        for w in todo:
            if snap_all.empty:
                break
            if snap_all[(snap_all.week == w) & (snap_all.scoring == scoring)].empty:
                continue
            frozen = store.select("expert_eval_pool", season=season, week=w, scoring=scoring, config_version=CONFIG_VERSION)
            pool = pool_from_db(frozen) if len(frozen) else None
            rows, pool_out, info = E.evaluate_week(season, w, scoring, snap_all, res_all[res_all.week == w], pool=pool)
            if pool is None and pool_out is not None:
                store.insert_missing("expert_eval_pool", pool_to_db(pool_out, season, w, scoring))
            if rows:
                df = pd.DataFrame(rows)
                df["season"], df["week"], df["scoring"], df["config_version"] = season, w, scoring, CONFIG_VERSION
                df["calc_at"] = datetime.now(timezone.utc).isoformat()
                store.upsert("expert_eval_scores", df[["season", "week", "source", "scoring", "config_version",
                                                       "position", "tier", "metric", "value", "n", "calc_at"]])
            # Real-world lineups: nobody is removed for late inactives (they score 0), so this is what a manager who
            # could not know the game-day inactive list would have lived with. Stored as rw_regret / rw_edge.
            frozen_rw = store.select("expert_eval_pool", season=season, week=w, scoring=scoring, config_version=REALWORLD_VERSION)
            pool_rw = pool_from_db(frozen_rw) if len(frozen_rw) else None
            rrows, rpool, _ = E.evaluate_week(season, w, scoring, snap_all, res_all[res_all.week == w], pool=pool_rw, policy="none")
            if pool_rw is None and rpool is not None:
                store.insert_missing("expert_eval_pool", pool_to_db(rpool, season, w, scoring, REALWORLD_VERSION))
            rw = pd.DataFrame([dict(r, metric={"regret": "rw_regret", "edge_regret": "rw_edge"}[r["metric"]]) for r in rrows
                               if r["metric"] in ("regret", "edge_regret") and r["position"] == "ALL"])
            if len(rw):
                rw["season"], rw["week"], rw["scoring"], rw["config_version"] = season, w, scoring, CONFIG_VERSION
                rw["calc_at"] = datetime.now(timezone.utc).isoformat()
                store.upsert("expert_eval_scores", rw[["season", "week", "source", "scoring", "config_version",
                                                       "position", "tier", "metric", "value", "n", "calc_at"]])
            summary[f"{scoring}/{w}"] = {"present": info["present"], "absent": info["absent"], "counts": info["counts"]}
            log(f"{scoring} week {w}: present={info['present']} absent={info['absent']} pool={info['pool']} {info['counts']}")

    refresh_weights(store, season, log=log)
    store.upsert("expert_eval_runs", [{
        "run_id": run_id, "season": season, "week": max(todo), "kind": "weekly", "config_version": CONFIG_VERSION,
        "inputs_hash": hash_rows(res_db), "notes": f"weeks={todo} skipped={skipped} result_changes={changes} cfg={config_hash()}"}])
    return {"weeks": todo, "skipped": skipped, "result_changes": changes, "info": summary}


def load_edges(store: Store, scoring: str) -> pd.DataFrame:
    """(season, week) x source matrix of overall regret edges across all stored seasons."""
    sc = store.select("expert_eval_scores", scoring=scoring, config_version=CONFIG_VERSION,
                      metric="edge_regret", position="ALL", tier="ALL")
    if sc.empty:
        return pd.DataFrame()
    p = sc.pivot_table(index=["season", "week"], columns="source", values="value").sort_index()
    return p


def refresh_weights(store: Store, season: int, log=print) -> None:
    """Recompute shadow weights from stored edges, for every week of every stored season, plus
    the next unplayed week. Strictly walk-forward: weights for week t only see weeks < t."""
    now = datetime.now(timezone.utc)
    for scoring in SCORINGS:
        edges = load_edges(store, scoring)
        if edges.empty:
            continue
        nxt = edges.index.max()
        edges_ext = pd.concat([edges, pd.DataFrame(np.nan, index=pd.MultiIndex.from_tuples([(nxt[0], nxt[1] + 1)], names=edges.index.names),
                                                   columns=edges.columns)])
        for wset in ("six", "three"):
            # skills are always estimated against the full six-expert field
            out = run_filter(edges_ext, SOURCES, scoring, "six") if wset == "six" else run_filter_three(edges_ext, scoring)
            out["calc_at"] = now.isoformat()
            store.upsert("expert_eval_weights", out)
        log(f"{scoring}: weights refreshed through week {nxt[1] + 1}")


def run_filter_three(edges_ext: pd.DataFrame, scoring: str) -> pd.DataFrame:
    """Three-expert strategy: skills are still estimated against the full six-expert field
    (so every expert's evidence is comparable), then only the three experts' weights are used."""
    full = run_filter(edges_ext, SOURCES, scoring, "three")
    return renormalize_subset(full, CORE_THREE)


def renormalize_subset(full: pd.DataFrame, members: list) -> pd.DataFrame:
    """Re-derive softmax/clip/rate-limit over a subset of experts from the full-field skill estimates."""
    from src.expert_eval.weights import softmax_weights
    out, prev = [], None
    for (season, week), g in full.groupby(["season", "week"], sort=True):
        sub = g[g.source.isin(members)].set_index("source")
        w, reason = softmax_weights(sub.skill_mean, prev)
        prev = w
        for s in members:
            r = sub.loc[s]
            out.append({**r.drop(labels=[]).to_dict(), "season": season, "week": week, "source": s,
                        "weight": float(w[s]), "equal_weight": 1 / len(members),
                        "reason": reason[s] or ("prior_only" if r.weeks_n == 0 else "tilt")})
    return pd.DataFrame(out)
