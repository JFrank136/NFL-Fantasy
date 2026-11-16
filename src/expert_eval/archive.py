"""Historical weekly rankings from Yahoo's fanPro endpoint (prior seasons).

Yahoo serves a past week's expert ranks on demand, but there are NO pull timestamps, so these can
never be proven "last published before kickoff". They are therefore labeled provenance='yahoo_archive',
evaluated under their own config_version (see ARCHIVE_VERSION) and never mixed into the live
(genuine pre-kickoff) series. `validate_archive` runs the checks that make a backfill defensible."""
import time

import numpy as np
import pandas as pd
import requests

from src.expert_eval.names import canon, norm_team
from src.sources import yahoo_weekly_consensus as yahoo

ARCHIVE_VERSION = "v1.1-archive"
EXPERTS = {"Justin Boone": "boone", "Joel Smyth": "smythe", "Matt Harmon": "harmon",
           "Scott Pianowski": "pianowski", "Hayden Winks": "winks"}
SCORING_SLUGS = {"half-ppr": "half-ppr", "ppr": "ppr"}


def fetch_archive(season: int, weeks, scorings=("half-ppr", "ppr"), delay=0.3, log=print) -> pd.DataFrame:
    """Rows: week, source, scoring, canon, position, raw_rank, scaled_rank (QB / FLX as published)."""
    sess, rows = requests.Session(), []
    for scoring in scorings:
        for w in weeks:
            for qp in ("QB", "FLX"):
                data = yahoo._fetch_position(qp, w, season, scoring, sess)
                ids = {eid: EXPERTS[n] for eid, n in data["expertNames"].items() if n in EXPERTS}
                for p in data["players"]:
                    pos = p.get("position")
                    if pos not in ("QB", "RB", "WR", "TE"):
                        continue
                    for eid, src in ids.items():
                        r = p.get("experts", {}).get(eid)
                        if r is None:
                            continue
                        rows.append((w, src, scoring, canon(p.get("name", "")), pos, norm_team(p.get("team")), int(r)))
                time.sleep(delay)
        log(f"fetched {scoring}: {len(rows)} rows so far")
    df = pd.DataFrame(rows, columns=["week", "source", "scoring", "canon", "position", "team", "raw_rank"])
    df = df[df.canon != ""].drop_duplicates(["week", "source", "scoring", "canon", "position"])
    df["scaled_rank"] = df.raw_rank.astype(float)
    df["pulled_at"] = pd.NaT
    df["provenance"] = "yahoo_archive"
    return df


def validate_archive(arch: pd.DataFrame, results: pd.DataFrame, scoring="half-ppr") -> dict:
    """Is the archive plausibly the as-published pre-game ranking, or was it re-ranked after the games?
    Post-hoc rankings correlate with outcomes far more strongly than genuine forecasts (~0.4-0.6)."""
    col = {"half-ppr": "pts_half", "ppr": "pts_ppr"}[scoring]
    a = arch[arch.scoring == scoring].merge(
        results[results.played][["week", "canon", "position", col]], on=["week", "canon", "position"], how="inner")
    out = {"coverage": arch.groupby(["source"]).week.nunique().to_dict(), "rows_per_source_week": int(arch.groupby(["source", "week"]).size().median())}
    corr = {}
    for (src, pos), g in a.groupby(["source", "position"]):
        if len(g) > 40:
            corr[f"{src}/{pos}"] = round(float(g.groupby("week").apply(lambda x: x.scaled_rank.rank().corr(-x[col].rank())).mean()), 3)
    out["mean_weekly_rank_corr"] = corr
    return out


def run_archive(season: int, store, weeks=range(1, 19), log=print) -> dict:
    """Additive backfill: labeled archive snapshots (provenance 'yahoo_archive'), the season's results, and scores
    under ARCHIVE_VERSION. Never touches live-series rows (different season / provenance / config_version) and never
    writes weights. Safe to rerun: snapshots and pools are insert-only, scores/results upsert on natural keys."""
    import uuid
    from datetime import datetime, timezone

    from src.expert_eval import evaluate as E, inputs, results as results_mod
    from src.expert_eval.config import SCORINGS, SPEC
    from src.expert_eval.pipeline import pool_to_db, results_to_db

    arch = fetch_archive(season, weeks, log=log)
    sched = inputs.load_schedule(season)
    arch = arch.merge(sched.rename(columns={"ko": "kickoff_at"}), on=["week", "team"], how="left")
    res = results_mod.build_results(season)
    snap_db = arch.rename(columns={"canon": "canonical_name"}).assign(season=season)[
        ["season", "week", "source", "scoring", "canonical_name", "position", "raw_rank", "scaled_rank", "pulled_at", "kickoff_at", "provenance"]]
    n_snap = store.insert_missing("expert_eval_snapshots", snap_db)
    store.upsert("expert_eval_results", results_to_db(res, season))
    n_scores = 0
    for scoring in SCORINGS:
        for w in sorted(arch.week.unique()):
            snap = arch[arch.scoring == scoring]
            rows, pool, info = E.evaluate_week(season, int(w), scoring, snap, res[res.week == w])
            if pool is None:
                continue
            store.insert_missing("expert_eval_pool", pool_to_db(pool, season, int(w), scoring, ARCHIVE_VERSION))
            df = pd.DataFrame(rows)
            df["season"], df["week"], df["scoring"], df["config_version"] = season, int(w), scoring, ARCHIVE_VERSION
            df["calc_at"] = datetime.now(timezone.utc).isoformat()
            n_scores += store.upsert("expert_eval_scores", df[["season", "week", "source", "scoring", "config_version",
                                                               "position", "tier", "metric", "value", "n", "calc_at"]])
    store.upsert("expert_eval_config", [{"version": ARCHIVE_VERSION, "spec": {**SPEC, "version": ARCHIVE_VERSION, "provenance": "yahoo_archive",
                                                                              "note": "ranks are not guaranteed to be pre-kickoff; exploratory only"}}])
    store.upsert("expert_eval_runs", [{"run_id": "archive-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:4],
                                       "season": season, "week": int(max(weeks)), "kind": "archive_backfill", "config_version": ARCHIVE_VERSION,
                                       "notes": f"snapshots={n_snap} scores={n_scores}; provenance=yahoo_archive; no weights written"}])
    return {"snapshots": n_snap, "scores": n_scores}
