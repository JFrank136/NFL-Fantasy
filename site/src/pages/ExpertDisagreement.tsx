import { useMemo, useState } from 'react'
import { useRosHistory } from '../lib/useRosHistory'
import { toBooneRosInput, toDsRosInput, type Scoring } from '../lib/useBlendedRos'
import { blendRosValues } from '../lib/blend'
import { buildMovers, describeBaseline, explainMissingBaseline, explainMissingWeekBaseline, splitSnapshots, weekSnapshot, TIMEFRAME_MIN_GAP_MS, type Timeframe } from '../lib/movers'
import { onlyWeek } from '../lib/freshness'
import { useCurrentWeek } from '../lib/useCurrentWeek'
import ColumnPicker, { toggleInSet } from '../components/ColumnPicker'
import { currentDisagreements, directionDisagreements } from '../lib/disagreement'

const POSITIONS = ['ALL', 'QB', 'RB', 'WR', 'TE']
const SCORINGS = ['ppr', 'half-ppr'] as const
const SCORING_LABELS: Record<Scoring, string> = { ppr: 'PPR', 'half-ppr': 'Half-PPR' }
const TIMEFRAMES: { id: Timeframe; label: string }[] = [
  { id: 'latest', label: 'Latest change' },
  { id: 'week', label: 'Since last week' },
]
const LIST_SIZE = 25
const CURRENT_COLUMNS = [
  { key: 'pos', label: 'Pos' },
  { key: 'dsRank', label: 'DS rank' },
  { key: 'booneRank', label: 'Boone rank' },
  { key: 'dsValue', label: 'DS value' },
  { key: 'booneScaled', label: 'Boone (DS scale)' },
]
const DIRECTION_COLUMNS = [
  { key: 'pos', label: 'Pos' },
  { key: 'booneChange', label: 'Boone change' },
  { key: 'dsChange', label: 'DS change' },
]

function ScoringToggle({ value, onChange }: { value: Scoring; onChange: (s: Scoring) => void }) {
  return (
    <div className="toggle-switch" role="tablist" aria-label="Scoring format">
      {SCORINGS.map(s => (
        <span
          key={s}
          role="tab"
          aria-selected={value === s}
          className={`toggle-switch-option ${value === s ? 'toggle-switch-option-active' : ''}`}
          onClick={() => onChange(s)}
        >
          {SCORING_LABELS[s]}
        </span>
      ))}
    </div>
  )
}

const r1 = (n: number) => Math.round(n * 10) / 10
const signed = (n: number) => `${n > 0 ? '+' : ''}${r1(n)}`
const signClass = (n: number) => (n > 0 ? 'signal-up' : n < 0 ? 'signal-down' : '')

export default function ExpertDisagreement() {
  const [view, setView] = useState<'current' | 'direction'>('current')
  const [scoring, setScoring] = useState<Scoring>('ppr')
  const [timeframe, setTimeframe] = useState<Timeframe>('latest')
  const [pos, setPos] = useState('ALL')
  const [hiddenCols, setHiddenCols] = useState<Set<string>>(new Set())
  const show = (key: string) => !hiddenCols.has(key)
  const { dsRows, booneRows, loading, error } = useRosHistory(scoring)
  const { week: currentWeek } = useCurrentWeek()
  const previousWeek = currentWeek != null ? currentWeek - 1 : null

  const data = useMemo(() => {
    // "Current" is always each source's newest pull per position -- gap-
    // independent, so any minGapMs works here (it only affects baseline).
    const ds = splitSnapshots(dsRows, TIMEFRAME_MIN_GAP_MS.latest)
    const boone = splitSnapshots(booneRows, TIMEFRAME_MIN_GAP_MS.latest)
    // A source's own newest pull can still be a stale week if it hasn't
    // refreshed since the NFL week turned over -- gate "current" to this
    // week's data so a lagging source drops out instead of blending in.
    const dsCurrentRows = onlyWeek(ds.current, currentWeek, r => r.as_of_week)
    const booneCurrentRows = onlyWeek(boone.current, currentWeek, r => r.week)
    const boonePending = currentWeek != null && boone.current.length > 0 && booneCurrentRows.length === 0
    const current = { ds: dsCurrentRows.map(toDsRosInput), boone: booneCurrentRows.map(r => toBooneRosInput(r, scoring)) }

    // "Since last week" wants the most recent pull actually tagged with the
    // PREVIOUS NFL week, not just a pull old enough by wall-clock time --
    // see weekSnapshot in movers.ts.
    const dsBase = timeframe === 'week'
      ? weekSnapshot(dsRows, previousWeek, r => r.as_of_week)
      : { rows: ds.baseline, times: ds.baselineTimes }
    const booneBase = timeframe === 'week'
      ? weekSnapshot(booneRows, previousWeek, r => r.week)
      : { rows: boone.baseline, times: boone.baselineTimes }
    const baseline = {
      ds: dsBase.rows.length ? dsBase.rows.map(toDsRosInput) : null,
      // A pending Boone has nothing in "current" at all, so comparing it
      // against a real week-old Boone baseline would misattribute Boone's
      // absence (not real movement) as a change.
      boone: !boonePending && booneBase.rows.length ? booneBase.rows.map(r => toBooneRosInput(r, scoring)) : null,
    }

    const dsMovers = buildMovers('ds', current, baseline)
    const booneMovers = buildMovers('booneScaled', current, baseline)
    return {
      currentRows: currentDisagreements(blendRosValues(current.ds, current.boone)),
      directionRows: directionDisagreements(dsMovers.rows, booneMovers.rows),
      directionAvailable: dsMovers.baselineAvailable && booneMovers.baselineAvailable,
      baselineDs: dsBase.times,
      baselineBoone: booneBase.times,
      freshest: dsCurrentRows.reduce((max, r) => (r.pulled_at > max ? r.pulled_at : max), ''),
      boonePending,
    }
  }, [dsRows, booneRows, scoring, timeframe, currentWeek, previousWeek])

  const matchesPos = (p: string) => pos === 'ALL' || p === pos
  const currentRows = useMemo(() => data.currentRows.filter(r => matchesPos(r.position)).slice(0, LIST_SIZE), [data, pos])
  const directionRows = useMemo(() => data.directionRows.filter(r => matchesPos(r.position)).slice(0, LIST_SIZE), [data, pos])

  return (
    <div className="space-y-3">
      <div className="card p-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex gap-1">
            <button className={`btn ${view === 'current' ? 'btn-primary' : ''}`} onClick={() => setView('current')}>Value gap</button>
            <button className={`btn ${view === 'direction' ? 'btn-primary' : ''}`} onClick={() => setView('direction')}>Opposite moves</button>
          </div>
          <ScoringToggle value={scoring} onChange={setScoring} />
          {data.freshest && <span className="subtle ml-auto">Data as of {new Date(data.freshest).toLocaleString()}</span>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {view === 'direction' && (
            <div className="flex gap-1">
              {TIMEFRAMES.map(t => (
                <button key={t.id} className={`btn ${timeframe === t.id ? 'btn-primary' : ''}`} onClick={() => setTimeframe(t.id)}>{t.label}</button>
              ))}
            </div>
          )}
          <div className="flex gap-1">
            {POSITIONS.map(p => (
              <button key={p} className={`btn ${pos === p ? 'btn-primary' : ''}`} onClick={() => setPos(p)}>{p}</button>
            ))}
          </div>
        </div>
        <ColumnPicker
          columns={view === 'current' ? CURRENT_COLUMNS : DIRECTION_COLUMNS}
          hidden={hiddenCols}
          onToggle={key => setHiddenCols(prev => toggleInSet(prev, key))}
        />
        <div className="subtle">
          {view === 'current' && 'Players Boone and Draft Sharks value most differently right now. Boone is converted to the Draft Sharks scale so the gap is fair. Players outside the top 150 in both are hidden.'}
          {view === 'direction' && `Players the two sources are moving in opposite directions on. Under 1.5 points of movement counts as flat. ${describeBaseline('Draft Sharks', data.baselineDs)} · ${describeBaseline('Boone', data.baselineBoone)}.`}
        </div>
        {loading && <div className="subtle">Loading…</div>}
        {error && <div style={{ color: 'var(--signal-down)' }}>Failed to load: {error}</div>}
        {!loading && !error && data.boonePending && (
          <div className="subtle">Boone hasn't updated ROS values for this week yet -- rows below reflect Draft Sharks only until it does.</div>
        )}
      </div>

      {!loading && !error && view === 'current' && (
        <div className="card p-3 sm:p-4">
          <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th className="sticky-col">Player</th>
                {show('pos') && <th>Pos</th>}
                {show('dsRank') && <th className="text-right">DS rank</th>}
                {show('booneRank') && <th className="text-right">Boone rank</th>}
                {show('dsValue') && <th className="text-right">DS value</th>}
                {show('booneScaled') && <th className="text-right">Boone (DS scale)</th>}
                <th className="text-right">Gap</th>
              </tr>
            </thead>
            <tbody>
              {currentRows.map(r => (
                <tr key={`${r.canonicalName}::${r.position}`}>
                  <td className="sticky-col">{r.playerName} {r.team && <span className="subtle">{r.team}</span>}</td>
                  {show('pos') && <td>{r.position}</td>}
                  {show('dsRank') && <td className="text-right">{r.dsRank}</td>}
                  {show('booneRank') && <td className="text-right">{r.booneRank}</td>}
                  {show('dsValue') && <td className="text-right">{r1(r.dsValue)}</td>}
                  {show('booneScaled') && <td className="text-right">{r1(r.booneScaled)}</td>}
                  <td className="text-right">
                    <span className={signClass(r.valueGap)}>{signed(r.valueGap)}</span>
                    <span className="subtle"> {r.valueGap > 0 ? 'Boone higher' : 'DS higher'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {currentRows.length === 0 && <div className="subtle">No players match.</div>}
        </div>
      )}

      {!loading && !error && view === 'direction' && !data.directionAvailable && (
        <div className="card p-4 space-y-1">
          <div className="subtle">Not enough history for this timeframe yet -- both sources need a baseline to compare against:</div>
          {!data.baselineDs.length && (
            <div className="subtle">
              {timeframe === 'week'
                ? explainMissingWeekBaseline('Draft Sharks', previousWeek)
                : explainMissingBaseline('Draft Sharks', dsRows, TIMEFRAME_MIN_GAP_MS.latest)}
            </div>
          )}
          {(data.boonePending || !data.baselineBoone.length) && (
            <div className="subtle">
              {data.boonePending
                ? `Boone hasn't updated ROS values for Week ${currentWeek} yet, so there's nothing current to compare.`
                : timeframe === 'week'
                  ? explainMissingWeekBaseline('Boone', previousWeek)
                  : explainMissingBaseline('Boone', booneRows, TIMEFRAME_MIN_GAP_MS.latest)}
            </div>
          )}
        </div>
      )}

      {!loading && !error && view === 'direction' && data.directionAvailable && (
        <div className="card p-3 sm:p-4">
          <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th className="sticky-col">Player</th>
                {show('pos') && <th>Pos</th>}
                {show('booneChange') && <th className="text-right">Boone change</th>}
                {show('dsChange') && <th className="text-right">DS change</th>}
                <th className="text-right">Difference</th>
              </tr>
            </thead>
            <tbody>
              {directionRows.map(r => (
                <tr key={`${r.canonicalName}::${r.position}`}>
                  <td className="sticky-col">{r.playerName} {r.team && <span className="subtle">{r.team}</span>}</td>
                  {show('pos') && <td>{r.position}</td>}
                  {show('booneChange') && <td className={`text-right ${signClass(r.booneChange)}`}>{signed(r.booneChange)}</td>}
                  {show('dsChange') && <td className={`text-right ${signClass(r.dsChange)}`}>{signed(r.dsChange)}</td>}
                  <td className="text-right font-semibold">{r1(r.size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {directionRows.length === 0 && <div className="subtle">No direction disagreements.</div>}
        </div>
      )}
    </div>
  )
}
