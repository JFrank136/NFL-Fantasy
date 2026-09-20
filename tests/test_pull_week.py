import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest

from pull_week import build_combos, call_with_retry
from src.sources.draftsharks_weekly import DraftSharksFetchError


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


def test_archival_yahoo_experts_are_registered_and_restricted():
    from pull_week import ALL_SOURCES, YAHOO_EXPERT_NAMES

    assert YAHOO_EXPERT_NAMES["harmon"] == "Matt Harmon"
    assert YAHOO_EXPERT_NAMES["pianowski"] == "Scott Pianowski"
    assert YAHOO_EXPERT_NAMES["winks"] == "Hayden Winks"
    assert set(YAHOO_EXPERT_NAMES) <= set(ALL_SOURCES)

    combos = build_combos(
        weeks=[1, 2, 3], sources=["harmon", "pianowski", "winks"],
        scorings=["half-ppr"], current_week=1, restrict_yahoo_to_current=True,
    )
    assert sorted(combos) == [
        (1, "harmon", "half-ppr"), (1, "pianowski", "half-ppr"), (1, "winks", "half-ppr"),
    ]


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


def test_call_with_retry_recovers_from_transient_failure():
    calls = []
    sleeps = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise DraftSharksFetchError("ssl eof")
        return "ok"

    assert call_with_retry(flaky, (DraftSharksFetchError,), delays=(5, 15), sleep=sleeps.append) == "ok"
    assert len(calls) == 3
    assert sleeps == [5, 15]


def test_call_with_retry_reraises_after_exhausting_attempts():
    calls = []

    def always_fails():
        calls.append(1)
        raise DraftSharksFetchError("down")

    with pytest.raises(DraftSharksFetchError):
        call_with_retry(always_fails, (DraftSharksFetchError,), delays=(1, 1), sleep=lambda _: None)
    assert len(calls) == 3


def test_call_with_retry_does_not_retry_other_errors():
    calls = []

    def bad_value():
        calls.append(1)
        raise ValueError("zero rows")

    with pytest.raises(ValueError):
        call_with_retry(bad_value, (DraftSharksFetchError,), delays=(1, 1), sleep=lambda _: None)
    assert len(calls) == 1
