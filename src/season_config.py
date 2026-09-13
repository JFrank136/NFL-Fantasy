"""Which weeks are still "active" (worth re-pulling) right now.

NFL weeks roll over on Tuesday (the last game of a week is Monday Night
Football; Tuesday is the first day of the next week's slate), so "active"
means "this week's Tuesday-to-Tuesday window hasn't fully elapsed yet" --
not "hasn't been played at all." Per Jared: keep refreshing a week's rankings
right up until it's actually over, not just until it starts.

WEEK_1_TUESDAY needs a one-line update at the start of each season -- it's
the Tuesday on/before that season's Week 1 kickoff (2026: the season opened
with a Wednesday game, so Week 1's rollover Tuesday is the day before it).
"""

from datetime import date, timedelta

SEASON = 2026
WEEK_1_TUESDAY = date(2026, 9, 8)
LAST_WEEK = 18


def current_week(today: date | None = None) -> int:
    """The earliest week that hasn't fully elapsed yet, clamped to
    [1, LAST_WEEK]. Before Week 1's rollover Tuesday, this is 1 -- there's
    nothing earlier to fall back to, and Week 1 rankings are exactly what's
    wanted in the days just before kickoff."""
    today = today or date.today()
    days_elapsed = (today - WEEK_1_TUESDAY).days
    week = days_elapsed // 7 + 1
    return max(1, min(week, LAST_WEEK))


def active_weeks(today: date | None = None) -> list[int]:
    """Every week from the current one through the end of the season --
    the set a "refresh everything that isn't done yet" run should pull."""
    return list(range(current_week(today), LAST_WEEK + 1))


def week_window(week: int) -> tuple[date, date]:
    """The [start, end) Tuesday-to-Tuesday date range for a given week --
    exposed mainly for tests/debugging, not used in the active-weeks decision
    itself."""
    start = WEEK_1_TUESDAY + timedelta(weeks=week - 1)
    return start, start + timedelta(weeks=1)
