"""Parsing test against a real captured fragment from
draftsharks.com/weekly-rankings/load-rows (2026-09-08, week 1 PPR) -- trimmed
to two rows, markup otherwise unmodified so this catches real structure
drift, not a hand-simplified stand-in."""

from src.sources.draftsharks_weekly import _parse_page

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
    data-percent-low="25"
    data-percent-high="15"
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
        <td class="ds-cell matchup centered" data-value="NO" data-attribute="matchup"><span class="column-title">NO</span></td>
        <td class="ds-cell ds-cell--pill strength-of-schedule centered" data-value="-13.3%" data-attribute="strength_of_schedule"><span class="column-title">-13.3%</span></td>
        <td class="ds-cell bye centered" data-value="6" data-attribute="player.team.bye"><span class="column-title">6</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="16.1" data-attribute="weeklyFloorPts"><span class="column-title">16.1</span></td>
        <td class="ds-cell consensus-proj centered" data-value="22.9" data-attribute="consensus_projection"><span class="column-title">22.9</span></td>
        <td class="ds-cell ds-proj centered" data-value="21.4" data-attribute="weeklyPts"><span class="column-title">21.4</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="24.6" data-attribute="weeklyCeilingPts"><span class="column-title">24.6</span></td>
        <td class="three-d-proj three-d-value highlight centered customizable-column" data-value="21.0" data-attribute="weekly3dPts"><span class="column-title">21.0</span></td>
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
    data-percent-low="6"
    data-percent-high="44"
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
        <td class="ds-cell matchup centered" data-value="@KC" data-attribute="matchup"><span class="column-title">@KC</span></td>
        <td class="ds-cell ds-cell--pill strength-of-schedule centered" data-value="-11.3%" data-attribute="strength_of_schedule"><span class="column-title">-11.3%</span></td>
        <td class="ds-cell bye centered" data-value="10" data-attribute="player.team.bye"><span class="column-title">10</span></td>
        <td class="ds-cell ds-cell--pill floor-proj centered" data-value="15.6" data-attribute="weeklyFloorPts"><span class="column-title">15.6</span></td>
        <td class="ds-cell consensus-proj centered" data-value="16.7" data-attribute="consensus_projection"><span class="column-title">16.7</span></td>
        <td class="ds-cell ds-proj centered" data-value="16.6" data-attribute="weeklyPts"><span class="column-title">16.6</span></td>
        <td class="ds-cell ds-cell--pill ceiling-proj centered" data-value="23.9" data-attribute="weeklyCeilingPts"><span class="column-title">23.9</span></td>
        <td class="three-d-proj three-d-value highlight centered customizable-column" data-value="17.9" data-attribute="weekly3dPts"><span class="column-title">17.9</span></td>
    </tr>
</tbody>
"""


def test_parses_both_rows():
    rows = _parse_page(REAL_FRAGMENT)
    assert len(rows) == 2


def test_first_row_fields():
    row = _parse_page(REAL_FRAGMENT)[0]
    assert row.source_player_id == "13542"
    assert row.player_name == "Jahmyr Gibbs"
    assert row.team == "DET"
    assert row.position == "RB"
    assert row.rank == 1
    assert row.matchup == "NO"
    assert row.bye == 6
    assert row.three_d_proj == 21.0
    assert row.is_rookie is False


def test_second_row_fields():
    row = _parse_page(REAL_FRAGMENT)[1]
    assert row.source_player_id == "34984"
    assert row.player_name == "Bo Nix"
    assert row.team == "DEN"
    assert row.matchup == "@KC"
    assert row.tier_overall == 7


def test_empty_fragment_returns_no_rows():
    assert _parse_page("<div>no rows here</div>") == []


def test_missing_matchup_is_none_not_a_crash():
    fragment = REAL_FRAGMENT.replace(
        '<td class="ds-cell matchup centered" data-value="NO" data-attribute="matchup">'
        '<span class="column-title">NO</span></td>',
        '<td class="ds-cell matchup centered" data-value="" data-attribute="matchup">'
        '<span class="column-title"></span></td>',
    )
    row = _parse_page(fragment)[0]
    assert row.matchup is None
