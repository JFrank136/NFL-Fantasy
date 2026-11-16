import numpy as np
import pandas as pd

from src.expert_eval import evaluate as E
from src.expert_eval.backtest import blend_ranks, bootstrap, gate_verdict
from src.expert_eval.pipeline import pool_from_db
from src.expert_eval.snapshots import scaled_ranks, select_snapshots
from src.expert_eval.store import _clean
from src.expert_eval.weights import clip_normalize, run_filter, softmax_weights


def _rankings(rows):
    df = pd.DataFrame(rows, columns=["week", "source", "scoring", "canon", "position", "team", "rank", "pulled_at"])
    df["pulled_at"] = pd.to_datetime(df.pulled_at, utc=True)
    return df


def test_snapshot_uses_latest_pull_before_kickoff_and_never_after():
    sched = pd.DataFrame({"week": [1], "team": ["KC"], "ko": [pd.Timestamp("2026-09-13 17:00", tz="UTC")]})
    r = _rankings([
        (1, "boone", "ppr", "a", "WR", "KC", 10, "2026-09-10 12:00"),
        (1, "boone", "ppr", "a", "WR", "KC", 7, "2026-09-13 15:00"),    # last before kickoff -> chosen
        (1, "boone", "ppr", "a", "WR", "KC", 1, "2026-09-13 18:00"),    # after kickoff -> must be ignored
    ])
    s = select_snapshots(r, sched)
    assert len(s) == 1 and s.iloc[0].raw_rank == 7


def test_snapshot_drops_stale_pulls_older_than_cap():
    sched = pd.DataFrame({"week": [5], "team": ["KC"], "ko": [pd.Timestamp("2026-10-11 17:00", tz="UTC")]})
    r = _rankings([(5, "draftsharks", "ppr", "a", "WR", "KC", 3, "2026-09-20 12:00")])
    assert select_snapshots(r, sched).empty


def test_draftsharks_overall_rank_rescaled_within_group_like_the_site():
    df = pd.DataFrame({"source": ["draftsharks"] * 4 + ["boone"], "week": 1, "scoring": "ppr",
                       "position": ["RB", "WR", "QB", "QB", "RB"], "raw_rank": [40, 12, 90, 5, 9]})
    out = scaled_ranks(df.assign(raw_rank=df.raw_rank.astype(float)))
    assert list(out[:4]) == [2, 1, 2, 1]        # FLEX: WR(12) then RB(40); QB: 5 then 90
    assert out.iloc[4] == 9                      # Yahoo experts used as published


def test_clip_normalize_respects_floor_and_cap_and_sums_to_one():
    w, _ = clip_normalize(np.array([0.7, 0.2, 0.05, 0.05]), floor=0.5, cap=1.8)
    assert abs(w.sum() - 1) < 1e-9
    assert w.max() <= 1.8 / 4 + 1e-9 and w.min() >= 0.5 / 4 - 1e-9


def test_rate_limit_caps_weekly_move():
    skill = pd.Series({"a": 5.0, "b": -5.0})
    prev = pd.Series({"a": 0.5, "b": 0.5})
    w, reason = softmax_weights(skill, prev)
    assert abs(w["a"] - 0.5) <= 0.18 / 2 + 1e-9 and reason["a"] == "rate_limited"


def _edges(mat, start=1):
    idx = pd.MultiIndex.from_tuples([(2026, start + i) for i in range(len(mat))], names=["season", "week"])
    return pd.DataFrame(mat, index=idx, columns=["a", "b", "c"])


def test_filter_does_not_tilt_on_pure_noise_early_and_uses_only_prior_weeks():
    rng = np.random.default_rng(0)
    e = _edges(rng.normal(0, 1.5, (3, 3)))
    out = run_filter(e, ["a", "b", "c"], "ppr", "six")
    wk1 = out[out.week == 1]
    assert np.allclose(wk1.weight, 1 / 3)               # nothing observed yet -> equal, reason prior_only
    assert (wk1.reason == "prior_only").all()
    # changing week 3's data must not change week 3's own weights
    e2 = e.copy(); e2.iloc[2] = [9, -9, 0]
    out2 = run_filter(e2, ["a", "b", "c"], "ppr", "six")
    assert np.allclose(out[out.week == 3].weight.values, out2[out2.week == 3].weight.values)


def test_filter_converges_toward_true_skill_but_stays_shrunk():
    rng = np.random.default_rng(1)
    true = np.array([1.0, 0.0, -1.0])
    e = _edges(true + rng.normal(0, 1.5, (60, 3)))
    last = run_filter(e, ["a", "b", "c"], "ppr", "six").query("week == 60").set_index("source")
    assert last.weight["a"] > last.weight["b"] > last.weight["c"]
    assert 0 < last.skill_mean["a"] < 1.0                # shrunk below the true +1.0


def test_absent_expert_gets_no_update_and_grows_uncertain():
    m = np.array([[1.0, 0.0, -1.0]] * 3 + [[1.0, 0.0, np.nan]] * 3)
    out = run_filter(_edges(m), ["a", "b", "c"], "ppr", "six")
    c3 = out[(out.source == "c") & (out.week == 4)].iloc[0]
    c6 = out[(out.source == "c") & (out.week == 6)].iloc[0]
    assert c6.weeks_n == c3.weeks_n and c6.skill_sd > c3.skill_sd


def test_blend_redistributes_weight_of_missing_source():
    raw = pd.DataFrame({"a": [1.0, np.nan], "b": [3.0, 5.0]})
    imp = raw.fillna(99)
    r = blend_ranks(raw, imp, {"a": 0.5, "b": 0.5}, pd.Series(["WR", "WR"]))
    assert list(r) == [2.0, 5.0]


def _pool():
    rows = []
    for pos, n in (("QB", 4), ("RB", 8), ("WR", 8), ("TE", 4)):
        for i in range(n):
            rows.append({"canon": f"{pos}{i}", "position": pos, "consensus": float(i + 1), "pos_rank": i + 1, "pts": float(20 - 2 * i)})
    return pd.DataFrame(rows)


def test_scenarios_are_deterministic_and_oracle_has_zero_regret():
    pool = _pool()
    a, b = E.Scenarios(pool, 123, n=200), E.Scenarios(pool, 123, n=200)
    assert all((a.idx[p] == b.idx[p]).all() for p in E.POS)
    pts = pool.pts.values
    # an expert ranking by actual points is the oracle: zero regret; a reversed one is strictly worse
    out = a.regret({"oracle": -pts, "worst": pts}, pts)
    assert np.allclose(out["oracle"]["total"], 0)
    assert out["worst"]["total"].mean() > 0
    comps = out["worst"]
    assert np.allclose(comps["QB"] + comps["RB"] + comps["WR"] + comps["TE"] + comps["FLEX"], comps["total"])


def test_pool_order_round_trips_through_storage_with_ties():
    p = _pool()
    p.loc[p.position == "RB", "consensus"] = 5.0           # all tied -> name must break the tie
    db = p.rename(columns={"canon": "canonical_name", "consensus": "consensus_rank"}).sample(frac=1, random_state=3)
    again = pool_from_db(db)
    built = p.assign(_p=p.position.map({q: i for i, q in enumerate(E.POS)})).sort_values(["_p", "consensus", "canon"]).reset_index(drop=True)
    assert list(again.canon) == list(built.canon)


def _avail_case():
    snap = pd.DataFrame({"week": 1, "scoring": "ppr", "source": "boone", "canon": list("abcdef"),
                         "position": "WR", "scaled_rank": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    res = pd.DataFrame({
        "canon": list("abcde"), "position": "WR", "pts_ppr": [10.0, 0.0, 0.0, 0.0, 0.0],
        "inactive": [False, True, True, False, False],
        "status": ["played", "inactive_roster", "inactive_roster", "questionable_dnp", "doubtful_dnp"],
        "roster_status": [None, "RES", "INA", "ACT", "ACT"],
        "report_status": [None, None, "Questionable", "Questionable", "Doubtful"]})
    return snap, res      # f has no result row at all


def test_default_policy_excludes_all_confirmed_unavailable_and_tracks_the_rest():
    pool, counts = E.build_pool(*_avail_case(), "ppr")
    assert list(pool.canon) == ["a", "d", "e", "f"]            # b (IR) and c (game-day inactive) removed
    assert counts["pool_excluded_unavailable"] == 2
    assert counts["pool_sat_questionable"] == 1 and counts["pool_sat_doubtful"] == 1 and counts["pool_no_result"] == 1


def test_known_early_policy_keeps_gameday_inactives_eligible_at_zero():
    from src.expert_eval.config import SPEC
    old = SPEC["inactive_policy"]
    try:
        SPEC["inactive_policy"] = "known_early"
        pool, counts = E.build_pool(*_avail_case(), "ppr")
        assert "c" in list(pool.canon) and "b" not in list(pool.canon)
        assert counts["pool_gameday_inactive_kept"] == 1
    finally:
        SPEC["inactive_policy"] = old


def test_bootstrap_and_gate_use_weeks_as_the_unit():
    d = np.array([0.5, 0.3, 0.4, 0.2, 0.6, 0.1, 0.5, 0.3])
    st = bootstrap(d)
    assert st["n_weeks"] == 8 and st["p_improve"] > 0.9
    assert gate_verdict(st, 0.01)["pass"]
    assert not gate_verdict({**st, "mean": 0.0}, 0.01)["pass"]


def test_store_clean_handles_nan_numpy_and_nested():
    assert _clean({"a": float("nan"), "b": [np.float64(1.5), np.int64(2)], "c": pd.Timestamp("2026-01-01", tz="UTC")}) == {
        "a": None, "b": [1.5, 2], "c": "2026-01-01T00:00:00+00:00"}


def test_frozen_tables_are_insert_only_but_results_can_be_corrected(tmp_path, monkeypatch):
    from src.expert_eval import store as store_mod
    monkeypatch.setattr(store_mod, "EXPORT_DIR", tmp_path)
    st = store_mod.Store(local_only=True)
    key = dict(season=2026, week=1, scoring="ppr", canonical_name="a", position="WR", config_version="v1.1")
    st.insert_missing("expert_eval_pool", [{**key, "consensus_rank": 1.0}])
    st.insert_missing("expert_eval_pool", [{**key, "consensus_rank": 9.0}])          # must be ignored
    assert st.select("expert_eval_pool").consensus_rank.tolist() == [1.0]
    rk = dict(season=2026, week=1, canonical_name="a", position="WR")
    st.upsert("expert_eval_results", [{**rk, "pts_ppr": 5.0}])
    st.upsert("expert_eval_results", [{**rk, "pts_ppr": 7.0}])                       # stat correction
    assert st.select("expert_eval_results").pts_ppr.tolist() == [7.0]


def test_result_changes_counts_stat_corrections_and_status_flips():
    from src.expert_eval.pipeline import _result_changes
    k = dict(season=2026, week=1, position="WR")
    old = pd.DataFrame([{**k, "canonical_name": "a", "pts_ppr": 5.0, "pts_std": 4.0, "status": "played"},
                        {**k, "canonical_name": "b", "pts_ppr": 0.0, "pts_std": 0.0, "status": "questionable_dnp"}])
    new = pd.DataFrame([{**k, "canonical_name": "a", "pts_ppr": 6.0, "pts_std": 4.0, "status": "played"},
                        {**k, "canonical_name": "b", "pts_ppr": 0.0, "pts_std": 0.0, "status": "inactive_roster"}])
    assert _result_changes(old, new) == 2
    assert _result_changes(old, old) == 0
