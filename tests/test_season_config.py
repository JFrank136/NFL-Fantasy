from datetime import date

from src.season_config import active_weeks, current_week, WEEK_1_TUESDAY, LAST_WEEK


def test_before_kickoff_is_week_1():
    assert current_week(WEEK_1_TUESDAY - date.resolution) == 1


def test_on_rollover_tuesday_is_that_week():
    assert current_week(WEEK_1_TUESDAY) == 1


def test_one_day_into_week_1_is_still_week_1():
    assert current_week(WEEK_1_TUESDAY.replace(day=WEEK_1_TUESDAY.day + 1)) == 1


def test_next_tuesday_rolls_to_week_2():
    from datetime import timedelta
    assert current_week(WEEK_1_TUESDAY + timedelta(weeks=1)) == 2


def test_far_future_clamps_to_last_week():
    from datetime import timedelta
    assert current_week(WEEK_1_TUESDAY + timedelta(weeks=52)) == LAST_WEEK


def test_active_weeks_runs_to_end_of_season():
    from datetime import timedelta
    weeks = active_weeks(WEEK_1_TUESDAY + timedelta(weeks=3))
    assert weeks == list(range(4, LAST_WEEK + 1))
