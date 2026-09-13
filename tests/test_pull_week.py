import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pull_week import build_combos


def test_all_mode_restricts_yahoo_sources_to_current_week():
    combos = build_combos(
        weeks=[1, 2, 3], sources=["draftsharks", "boone", "smythe"],
        scorings=["half-ppr"], current_week=1, restrict_yahoo_to_current=True,
    )
    draftsharks_weeks = sorted(w for w, s, sc in combos if s == "draftsharks")
    boone_weeks = sorted(w for w, s, sc in combos if s == "boone")
    smythe_weeks = sorted(w for w, s, sc in combos if s == "smythe")
    assert draftsharks_weeks == [1, 2, 3]
    assert boone_weeks == [1]
    assert smythe_weeks == [1]


def test_explicit_week_list_is_not_restricted():
    combos = build_combos(
        weeks=[5], sources=["boone"], scorings=["half-ppr"],
        current_week=1, restrict_yahoo_to_current=False,
    )
    assert combos == [(5, "boone", "half-ppr")]


def test_draftsharks_never_restricted():
    combos = build_combos(
        weeks=[1, 2, 3, 4], sources=["draftsharks"], scorings=["ppr"],
        current_week=1, restrict_yahoo_to_current=True,
    )
    assert sorted(w for w, s, sc in combos) == [1, 2, 3, 4]
