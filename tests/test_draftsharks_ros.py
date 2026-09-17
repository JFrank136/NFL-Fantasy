"""Parsing test against a constructed fragment shaped like
draftsharks.com/ros-rankings/load-rows -- same tbody[data-player-row]
structure weekly-rankings/load-rows uses, with ROS-specific data-attribute
names (rosWeeklyPts/rosWeeklyFloorPts/rosWeeklyCeilingPts/dsValue/
games_played/player.sipPlayerProfile.injury_prob) substituted in. Not a
live-captured fragment (no live sample was available while writing this) --
verify parsing against a real captured page the first time this runs
against the live endpoint, and update this fixture if field names differ."""

from src.sources.draftsharks_ros import _parse_page, fetch_draftsharks_ros

REAL_FRAGMENT = """
<tbody
    data-player-row
    data-key="13542"
    data-tier-overall="1"
    data-tier-positional="1"
    data-fantasy-position="RB"
    data-player-name="Jahmyr Gibbs"
    data-team-id="11"
    data-is-rookie="false"
    class=""
    x-show="isVisibleRow($el)">

    <tr class="player-row">
        <td class="ds-cell ds-cell--lg rank centered">
            <div class="column-title rank-index">
                <span>1</span>
            </div>
        </td>
        <td class="player-cell player-name no-center sticky-left">
            <img class="team-badge" src="/img/icons/teams/DET.svg" alt="DET logo" loading="lazy" />
        </td>
        <td class="ds-cell strength-of-schedule centered" data-value="-3.9%" data-attribute="strength_of_schedule"><span class="column-title">-3.9%</span></td>
        <td class="ds-cell bye centered" data-value="6" data-attribute="player.team.bye"><span class="column-title">6</span></td>
        <td class="ds-cell games-played centered" data-value="12" data-attribute="games_played"><span class="column-title">12</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="180.5" data-attribute="rosWeeklyFloorPts"><span class="column-title">180.5</span></td>
        <td class="ds-cell ros-proj centered" data-value="220.4" data-attribute="rosWeeklyPts"><span class="column-title">220.4</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="260.1" data-attribute="rosWeeklyCeilingPts"><span class="column-title">260.1</span></td>
        <td class="three-d-proj three-d-value highlight centered" data-value="95.0" data-attribute="dsValue"><span class="column-title">95.0</span></td>
        <td class="ds-cell injury-risk centered" data-value="8" data-attribute="player.sipPlayerProfile.injury_prob"><span class="column-title">8</span></td>
    </tr>
</tbody>

<tbody
    data-player-row
    data-key="34984"
    data-tier-overall="7"
    data-tier-positional="2"
    data-fantasy-position="QB"
    data-player-name="Bo Nix"
    data-team-id="10"
    data-is-rookie="false"
    class=""
    x-show="isVisibleRow($el)">

    <tr class="player-row">
        <td class="ds-cell ds-cell--lg rank centered">
            <div class="column-title rank-index">
                <span>26</span>
            </div>
        </td>
        <td class="player-cell player-name no-center sticky-left">
            <img class="team-badge" src="/img/icons/teams/DEN.svg" alt="DEN logo" loading="lazy" />
        </td>
        <td class="ds-cell strength-of-schedule centered" data-value="-11.3%" data-attribute="strength_of_schedule"><span class="column-title">-11.3%</span></td>
        <td class="ds-cell bye centered" data-value="10" data-attribute="player.team.bye"><span class="column-title">10</span></td>
        <td class="ds-cell games-played centered" data-value="13" data-attribute="games_played"><span class="column-title">13</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="150.6" data-attribute="rosWeeklyFloorPts"><span class="column-title">150.6</span></td>
        <td class="ds-cell ros-proj centered" data-value="180.7" data-attribute="rosWeeklyPts"><span class="column-title">180.7</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="210.9" data-attribute="rosWeeklyCeilingPts"><span class="column-title">210.9</span></td>
        <td class="three-d-proj three-d-value highlight centered" data-value="72.0" data-attribute="dsValue"><span class="column-title">72.0</span></td>
        <td class="ds-cell injury-risk centered" data-value="3" data-attribute="player.sipPlayerProfile.injury_prob"><span class="column-title">3</span></td>
    </tr>
</tbody>

<tbody
    data-player-row
    data-key="99001"
    data-tier-overall="9"
    data-tier-positional="9"
    data-fantasy-position="DEF"
    data-player-name="Denver Broncos"
    data-team-id="10"
    data-is-rookie="false"
    class=""
    x-show="isVisibleRow($el)">

    <tr class="player-row">
        <td class="ds-cell ds-cell--lg rank centered">
            <div class="column-title rank-index">
                <span>150</span>
            </div>
        </td>
        <td class="player-cell player-name no-center sticky-left">
            <img class="team-badge" src="/img/icons/teams/DEN.svg" alt="DEN logo" loading="lazy" />
        </td>
        <td class="ds-cell strength-of-schedule centered" data-value="1.0%" data-attribute="strength_of_schedule"><span class="column-title">1.0%</span></td>
        <td class="ds-cell bye centered" data-value="10" data-attribute="player.team.bye"><span class="column-title">10</span></td>
        <td class="ds-cell games-played centered" data-value="13" data-attribute="games_played"><span class="column-title">13</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="60.0" data-attribute="rosWeeklyFloorPts"><span class="column-title">60.0</span></td>
        <td class="ds-cell ros-proj centered" data-value="80.0" data-attribute="rosWeeklyPts"><span class="column-title">80.0</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="100.0" data-attribute="rosWeeklyCeilingPts"><span class="column-title">100.0</span></td>
        <td class="three-d-proj three-d-value highlight centered" data-value="20.0" data-attribute="dsValue"><span class="column-title">20.0</span></td>
        <td class="ds-cell injury-risk centered" data-value="0" data-attribute="player.sipPlayerProfile.injury_prob"><span class="column-title">0</span></td>
    </tr>
</tbody>
"""


def test_parses_all_rows_including_non_fantasy_positions():
    rows = _parse_page(REAL_FRAGMENT)
    assert len(rows) == 3  # _parse_page itself does NOT filter positions


def test_first_row_fields():
    row = _parse_page(REAL_FRAGMENT)[0]
    assert row.source_player_id == "13542"
    assert row.player_name == "Jahmyr Gibbs"
    assert row.team == "DET"
    assert row.position == "RB"
    assert row.rank == 1
    assert row.tier_overall == 1
    assert row.tier_positional == 1
    assert row.strength_of_schedule == "-3.9%"
    assert row.bye == 6
    assert row.games_played == 12
    assert row.floor_proj == 180.5
    assert row.projection == 220.4
    assert row.ceiling_proj == 260.1
    assert row.ds_value == 95.0
    assert row.injury_risk == "8"


def test_empty_fragment_returns_no_rows():
    assert _parse_page("<div>no rows here</div>") == []


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _FakeSession:
    """Returns one fragment per call, then an empty page, recording the
    offset/params each call was made with so pagination can be asserted."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params, headers, timeout):
        self.calls.append(params)
        if self.pages:
            return _FakeResponse(self.pages.pop(0))
        return _FakeResponse("")


def test_fetch_paginates_until_empty_page_and_filters_to_offense_positions():
    session = _FakeSession([REAL_FRAGMENT])
    rows = fetch_draftsharks_ros("half-ppr", request_delay=0, session=session)

    # 3 rows in the fragment, but only RB/QB are kept -- DEF is dropped.
    assert len(rows) == 2
    assert {r.position for r in rows} == {"RB", "QB"}

    # First call at offset 0; since the only page returned fewer rows than
    # a full page, fetch stops after one call (no second, empty-page call
    # needed -- same short-circuit draftsharks_weekly.py's fetch uses).
    assert len(session.calls) == 1
    assert session.calls[0]["offset"] == 0
    assert session.calls[0]["fantasyPosition"] == ""
    assert session.calls[0]["pprSuperflexSlug"] == "half-ppr"
