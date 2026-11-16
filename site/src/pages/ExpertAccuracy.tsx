import { useMemo, useState } from 'react'
import ScoringToggle from '../components/ScoringToggle'
import type { Scoring } from '../lib/useBlendedRos'
import {
  buildPositionEdges, buildSummary, buildUnavailable, buildTierAccuracy, edgeHistory, evidenceLabel, expertLabel, POSITION_COMPONENTS,
  TIER_LABELS, TIERS, useExpertEval, weightHistory, type BacktestComparison, type HistoryGrid,
} from '../lib/expertEval'

const r1 = (n: number) => Math.round(n * 10) / 10
const r2 = (n: number) => Math.round(n * 100) / 100
const signed = (n: number, d = 2) => `${n > 0 ? '+' : ''}${n.toFixed(d)}`
const pct = (n: number, d = 0) => `${(n * 100).toFixed(d)}%`
const signClass = (n: number | null) => (n == null ? '' : n > 0.05 ? 'signal-up' : n < -0.05 ? 'signal-down' : '')

// Everything is measured against the site's current static weights (the incumbent). Candidates are the only
// strategies eligible for promotion; the rest are references/diagnostics.
const STRATEGY_LABELS: [string, string][] = [
  ['anchor20dyn', 'Candidate: static weights 80% + extra experts 20% (split by learned skill)'],
  ['blend50', 'Candidate: 50% learned six-expert weights + 50% static'],
  ['dyn6', 'Learned weights, 6 experts (reference)'],
  ['dyn3', 'Learned weights, 3 experts (reference)'],
  ['equal6', 'Equal weights, 6 experts (reference)'],
  ['equal3', 'Equal weights, 3 experts (reference)'],
  ['anchor10', 'Static + extras at 10% (diagnostic)'],
  ['anchor20', 'Static + extras at 20% (diagnostic)'],
  ['anchor30', 'Static + extras at 30% (diagnostic)'],
  ['plus_harmon', 'Static + Harmon at 15% (diagnostic)'],
  ['plus_pianowski', 'Static + Pianowski at 15% (diagnostic)'],
  ['plus_winks', 'Static + Winks at 15% (diagnostic)'],
]

function HistoryTable({ grid, format, caption }: { grid: HistoryGrid; format: (n: number) => string; caption: string }) {
  if (!grid.weeks.length) return null
  return (
    <div className="card p-3 sm:p-4 space-y-2">
      <span className="label">{caption}</span>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th className="sticky-col">Expert</th>
              {grid.weeks.map(w => <th key={`${w.season}-${w.week}`} className="text-right">Wk {w.week}</th>)}
            </tr>
          </thead>
          <tbody>
            {grid.sources.map(s => (
              <tr key={s}>
                <td className="sticky-col">{expertLabel(s)}</td>
                {grid.weeks.map(w => {
                  const v = grid.value(s, w.season, w.week)
                  return <td key={`${w.season}-${w.week}`} className="text-right">{v == null ? '—' : format(v)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BacktestCard({ comparisons, weeks }: { comparisons: Record<string, BacktestComparison>; weeks: number[] }) {
  const rows = STRATEGY_LABELS.filter(([k]) => comparisons[`${k}_vs_static3`])
  if (!rows.length) return null
  return (
    <div className="card p-3 sm:p-4 space-y-2">
      <span className="label">Does anything beat the site's current weights? (weeks {weeks[0]}–{weeks[weeks.length - 1]})</span>
      <p className="subtle text-sm">
        The benchmark is the static weights Rankings uses today; "Saved" is lineup points per week each strategy gains over them (negative = worse).
        Any learned weights only use earlier weeks. Weeks are the unit of evidence, so these are {weeks.length} observations, and the range is 80%.
        A candidate must beat the benchmark in both scoring formats before it can be promoted. Equal weighting is shown for reference.
      </p>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th className="sticky-col">Comparison</th>
              <th className="text-right">Saved / wk</th>
              <th className="text-right">80% range</th>
              <th className="text-right">Chance it helps</th>
              <th className="text-right">Weeks worse</th>
              <th className="text-right">Worst week</th>
              <th className="text-right">Vs equal (6)</th>
              <th>Promotion gate</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, label]) => {
              const c = comparisons[`${name}_vs_static3`]
              const eq = comparisons[`${name}_vs_equal6`]
              return (
                <tr key={name}>
                  <td className="sticky-col">{label}</td>
                  <td className={`text-right ${signClass(c.mean)}`}>{signed(c.mean)}</td>
                  <td className="text-right">{signed(c.lo)} to {signed(c.hi)}</td>
                  <td className="text-right">{pct(c.p_improve)}</td>
                  <td className="text-right">{pct(c.share_weeks_worse)}</td>
                  <td className="text-right">{signed(c.worst_week, 1)}</td>
                  <td className={`text-right ${signClass(eq?.mean ?? null)}`}>{eq ? signed(eq.mean) : '—'}</td>
                  <td>
                    {c.gate == null ? <span className="subtle">n/a</span>
                      : c.gate.pass ? 'Meets thresholds'
                      : <span className="subtle">Not yet ({Object.entries(c.gate.checks).filter(([, ok]) => !ok).map(([n]) => n.replace('_', ' ')).join(', ')})</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function ExpertAccuracy() {
  const [scoring, setScoring] = useState<Scoring>('half-ppr')
  const { scores, weights, backtest, loading, error } = useExpertEval(scoring)

  const summary = useMemo(() => buildSummary(scores, weights), [scores, weights])
  const posEdges = useMemo(() => buildPositionEdges(scores), [scores])
  const tiers = useMemo(() => buildTierAccuracy(scores), [scores])
  const unavailable = useMemo(() => buildUnavailable(scores), [scores])
  const edgeGrid = useMemo(() => edgeHistory(scores), [scores])
  const weightGrid = useMemo(() => weightHistory(weights, 'six'), [weights])
  const nextWeek = weights.length ? Math.max(...weights.map(w => w.week)) : null
  const evidenceWeeks = summary.length ? Math.max(...summary.map(s => s.weeks)) : 0

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">Expert Accuracy</h1>
          <ScoringToggle value={scoring} onChange={setScoring} />
        </div>
        <div className="card p-3 sm:p-4 space-y-1">
          <span className="label">Shadow mode</span>
          <p className="text-sm">
            These weights are computed and tracked every week but are <strong>not used by the Rankings page yet</strong>. Rankings still uses its fixed weights
            until the backtest below gives enough evidence to switch.
          </p>
          <p className="subtle text-sm">
            Each week, every expert's ranking is graded by the lineup it would have produced: with 2 RB, 2 WR, 1 TE, 1 QB and a flex from random rosters, how many
            points were left on the table compared with the best possible lineup. "Edge" is how many points per week an expert beat the average expert.
            {evidenceWeeks > 0 && <> Evidence so far: {evidenceWeeks} weeks.</>}
          </p>
        </div>
      </div>

      {loading && <p className="subtle">Loading expert accuracy…</p>}
      {error && <p className="signal-down">Could not load: {error}</p>}
      {!loading && !error && summary.length === 0 && <p className="subtle">No evaluated weeks yet. The first results appear after a week's games are final.</p>}

      {summary.length > 0 && (
        <div className="card p-3 sm:p-4 space-y-2">
          <span className="label">Experts, evidence and shadow weights{nextWeek != null ? ` (for week ${nextWeek})` : ''}</span>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="sticky-col">Expert</th>
                  <th className="text-right">Weeks</th>
                  <th className="text-right">Avg edge (pts/wk)</th>
                  <th className="text-right">Real-world edge</th>
                  <th className="text-right">Skill estimate</th>
                  <th className="text-right">Chance above field</th>
                  <th className="text-right">Weight</th>
                  <th className="text-right">Change</th>
                  <th className="text-right">Weight in 3-expert blend</th>
                  <th>Read</th>
                </tr>
              </thead>
              <tbody>
                {[...summary].sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0)).map(s => {
                  const change = s.weight != null && s.prevWeight != null ? s.weight - s.prevWeight : null
                  return (
                    <tr key={s.source}>
                      <td className="sticky-col">{expertLabel(s.source)}</td>
                      <td className="text-right">{s.weeks}</td>
                      <td className={`text-right ${signClass(s.avgEdge)}`}>
                        {s.avgEdge == null ? '—' : <>{signed(s.avgEdge)}{s.edgeSe != null && <span className="subtle"> ±{r2(s.edgeSe)}</span>}</>}
                      </td>
                      <td className={`text-right ${signClass(s.avgRwEdge)}`}>{s.avgRwEdge == null ? '—' : signed(s.avgRwEdge)}</td>
                      <td className={`text-right ${signClass(s.skillMean)}`}>
                        {s.skillMean == null ? '—' : <>{signed(s.skillMean)}{s.skillSd != null && <span className="subtle"> ±{r2(s.skillSd)}</span>}</>}
                      </td>
                      <td className="text-right">{s.pBetter == null ? '—' : pct(s.pBetter)}</td>
                      <td className="text-right">{s.weight == null ? '—' : <>{pct(s.weight, 1)}<span className="subtle"> (equal {pct(s.equalWeight ?? 0, 1)})</span></>}</td>
                      <td className={`text-right ${signClass(change == null ? null : change * 20)}`}>{change == null ? '—' : `${change > 0 ? '+' : ''}${(change * 100).toFixed(1)} pts`}</td>
                      <td className="text-right">{s.threeWeight == null ? <span className="subtle">—</span> : pct(s.threeWeight, 1)}</td>
                      <td className="subtle">{evidenceLabel(s.weeks, s.pBetter)}{s.reason && s.reason !== 'tilt' ? ` · ${s.reason.replace('_', ' ')}` : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="subtle text-sm">
            Edge grades the ranking itself (players ruled inactive on game day are removed for everyone). Real-world edge keeps them in as zeros,
            i.e. what a manager who could not know the inactive list would have lived with.
            Skill estimate shrinks each expert's raw average toward zero (the field) and widens when evidence is thin. Weights start equal and move only as that
            estimate does, capped at 0.5×–1.8× an equal share and limited in how far they can move in a week.
          </p>
        </div>
      )}

      {backtest && <BacktestCard comparisons={backtest.summary.comparisons} weeks={backtest.summary.weeks} />}

      {posEdges.length > 0 && (
        <div className="card p-3 sm:p-4 space-y-2">
          <span className="label">Where each expert gains or loses (avg edge, pts/wk)</span>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th className="sticky-col">Expert</th>{POSITION_COMPONENTS.map(p => <th key={p} className="text-right">{p === 'FLEX' ? 'Flex pick' : p}</th>)}</tr>
              </thead>
              <tbody>
                {posEdges.map(r => (
                  <tr key={r.source}>
                    <td className="sticky-col">{expertLabel(r.source)}</td>
                    {POSITION_COMPONENTS.map(p => {
                      const c = r.byPos[p]
                      return <td key={p} className={`text-right ${signClass(c?.mean ?? null)}`}>{c ? signed(c.mean) : '—'}</td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle text-sm">Tracked for later; position-specific weights are not used yet. Slices have less evidence than the overall number, so treat single differences cautiously.</p>
        </div>
      )}

      {tiers.length > 0 && (
        <div className="card p-3 sm:p-4 space-y-2">
          <span className="label">Start/sit accuracy by ranking tier</span>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th className="sticky-col">Expert</th>{TIERS.map(t => <th key={t} className="text-right">{TIER_LABELS[t]}</th>)}</tr>
              </thead>
              <tbody>
                {tiers.map(r => (
                  <tr key={r.source}>
                    <td className="sticky-col">{expertLabel(r.source)}</td>
                    {TIERS.map(t => {
                      const c = r.byTier[t]
                      return <td key={t} className="text-right">{c ? pct(c.acc, 1) : '—'}</td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle text-sm">How often the expert ranked the higher scorer first, for same-position players within six spots of each other in consensus. 50% is a coin flip.</p>
        </div>
      )}

      {unavailable.length > 0 && (
        <div className="card p-3 sm:p-4 space-y-2">
          <span className="label">Late-news exposure</span>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th className="sticky-col">Expert</th><th className="text-right">Ranked starters later ruled out (per week)</th><th className="text-right">Weeks</th></tr></thead>
              <tbody>
                {[...unavailable].sort((a, b) => (a.perWeek ?? 0) - (b.perWeek ?? 0)).map(u => (
                  <tr key={u.source}><td className="sticky-col">{expertLabel(u.source)}</td><td className="text-right">{u.perWeek == null ? '—' : r1(u.perWeek)}</td><td className="text-right">{u.weeks}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="subtle text-sm">
            Players who were game-day inactive, on IR or ruled Out are removed from the scored lineups for every expert, so nobody is graded on news they could not have had.
            This table keeps that cost visible: among each expert's own top picks at each position, how many turned out to be unavailable. Fewer is better.
          </p>
        </div>
      )}

      <HistoryTable grid={weightGrid} format={n => pct(n, 1)} caption="Shadow weight by week (6 experts)" />
      <HistoryTable grid={edgeGrid} format={n => signed(n, 1)} caption="Weekly edge vs the average expert (pts)" />
      <p className="subtle text-sm">
        Evaluation uses each player's last ranking before their own kickoff, excludes players confirmed out, and counts weeks (not simulated rosters) as the
        independent observations. Updated after each week's games are final; history accumulates across seasons.
      </p>
    </div>
  )
}
