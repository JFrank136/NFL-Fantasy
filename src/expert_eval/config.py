"""Versioned evaluation settings. Any change to a field that affects scores means
a new CONFIG_VERSION (and a rescore), never an in-place edit -- stored scores carry
the version they were computed under."""
import hashlib
import json

CONFIG_VERSION = "v1.1"
REALWORLD_VERSION = CONFIG_VERSION + "-rw"   # pool version for the no-hindsight (real-world) lineup metric

SOURCES = ["draftsharks", "boone", "smythe", "harmon", "pianowski", "winks"]
CORE_THREE = ["draftsharks", "boone", "smythe"]
SCORINGS = ["half-ppr", "ppr"]
SCORING_COL = {"half-ppr": "pts_half", "ppr": "pts_ppr"}

# Site's current static weights (site/src/lib/consensusWeights.ts, hand-copied).
STATIC_WEIGHTS = {
    "default": {"draftsharks": 0.50, "boone": 0.30, "smythe": 0.20},
    "QB": {"draftsharks": 0.40, "boone": 0.40, "smythe": 0.20},
}

SPEC = {
    "version": CONFIG_VERSION,
    # Roster scenarios: uniform draws from a starter-relevant pool, standard 1QB lineup.
    "pool_size": {"QB": 14, "RB": 28, "WR": 34, "TE": 14},
    "roster": {"QB": 2, "RB": 5, "WR": 5, "TE": 2},
    "starters": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1},
    "n_scenarios": 2000,
    "seed_salt": "ee-v1",
    # An expert ranking fewer than this share of the pool is treated as not publishing that week.
    "min_coverage": 0.5,
    "max_snapshot_age_days": 8,
    # Which unavailable players are removed from lineup choices (same for every expert):
    #   all_confirmed: game-day inactives (INA), IR/cut/practice-squad, injury-report Out
    #   known_early:   only IR/cut/practice-squad/Out (game-day inactives stay eligible, score 0)
    #   none:          nobody removed (everyone who did not play scores 0)
    "inactive_policy": "all_confirmed",
    # Unranked-in-pool players take the expert's own max scaled rank in that group + 1.
    "impute": "max_rank_plus_one",
    # Pairwise diagnostics.
    "pair_gap": 6,
    "tiers": {"T1": [1, 6], "T2": [7, 12], "T3": [13, 24], "T4": [25, 999]},
    # Weighting engine (placeholders to be settled by the walk-forward backtest, not by hand).
    "weights": {
        "tau0": 0.5,        # prior sd of true skill (points/week)
        "q": 0.01,          # per-week drift variance of true skill
        "q_season": 0.10,   # extra variance added at a season boundary
        "sigma_default": 1.5,   # weekly edge noise sd until enough weeks exist to estimate it
        "sigma_min_weeks": 4,
        "beta": 1.0,        # softmax temperature on posterior skill (per point)
        "floor": 0.5,       # min weight as a multiple of equal share
        "cap": 1.8,         # max weight as a multiple of equal share
        "max_step": 0.18,   # max weekly weight change = max_step / K
    },
    # Promotion gate thresholds (fixed before looking at backtest results).
    # Promotion gate. The PRIMARY benchmark is the incumbent static weights (STATIC_WEIGHTS); equal weighting is
    # reported as a secondary benchmark only. A candidate must pass in BOTH scoring formats.
    "gate": {
        "benchmark": "static3",
        "secondary_benchmark": "equal6",
        "require_both_formats": True,
        "min_improvement": 0.10,     # points/week of regret saved vs equal weights
        "min_p_improve": 0.70,       # week-bootstrap P(improvement > 0)
        "max_share_weeks_worse": 0.55,
        "max_worst_week_deficit": 4.0,
        "max_avg_turnover": 0.08,    # mean per-week sum |dw|/2
        "max_perm_p": 0.10,          # exact permutation p (skills reassigned to random experts), six-expert only
    },
}


def config_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()[:12]
