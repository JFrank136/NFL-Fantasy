// src/lib/expertEval.ts
//
// Read-side helpers for the Expert Accuracy page (shadow weighting evidence).
// Pure builders over rows from the expert_eval_* tables written by
// in-season/src/expert_eval (python). Nothing here feeds the live Rankings blend.

import { useEffect, useState } from 'react'
import { fetchAllRows, supabase } from './supabase'

export const EVAL_CONFIG_VERSION = 'v1.1'

export type EvalScoring = 'half-ppr' | 'ppr'

export interface ScoreRow {
  season: number
  week: number
  source: string
  position: string
  tier: string
  metric: string
  value: number | null
  n: number | null
}

export interface WeightRow {
  season: number
  week: number
  weight_set: 'six' | 'three'
  source: string
  weight: number
  equal_weight: number
  skill_mean: number | null
  skill_sd: number | null
  p_better: number | null
  weeks_n: number | null
  raw_mean: number | null
  reason: string | null
}

export interface BacktestComparison {
  mean: number
  lo: number
  hi: number
  p_improve: number
  share_weeks_worse: number
  worst_week: number
  n_weeks: number
  turnover: number | null
  perm_p?: number | null
  gate: { pass: boolean; checks: Record<string, boolean> } | null
}

export interface BacktestRow {
  run_id: string
  created_at: string
  summary: { weeks: number[]; mean_regret: Record<string, number>; comparisons: Record<string, BacktestComparison>; both_formats_pass?: Record<string, boolean> }
}

export const EXPERT_LABELS: Record<string, string> = {
  draftsharks: 'Draft Sharks',
  boone: 'Justin Boone',
  smythe: 'Joel Smyth',
  harmon: 'Matt Harmon',
  pianowski: 'Scott Pianowski',
  winks: 'Hayden Winks',
}
export const expertLabel = (s: string) => EXPERT_LABELS[s] ?? s

const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null)
const sd = (xs: number[]) => {
  if (xs.length < 2) return null
  const m = mean(xs) as number
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1))
}

/** Experts present in the data, in a stable display order (known six first, then any new source). */
export function expertsIn(rows: { source: string }[]): string[] {
  const seen = new Set(rows.map(r => r.source).filter(s => s !== 'field'))
  const known = Object.keys(EXPERT_LABELS).filter(s => seen.has(s))
  return [...known, ...[...seen].filter(s => !known.includes(s)).sort()]
}

export function latestWeekKey(rows: { season: number; week: number }[]): { season: number; week: number } | null {
  if (!rows.length) return null
  return rows.reduce((a, b) => (b.season > a.season || (b.season === a.season && b.week > a.week) ? b : a))
}

export interface ExpertSummaryRow {
  source: string
  weeks: number
  avgEdge: number | null
  edgeSe: number | null
  avgRwEdge: number | null
  skillMean: number | null
  skillSd: number | null
  pBetter: number | null
  weight: number | null
  equalWeight: number | null
  prevWeight: number | null
  threeWeight: number | null
  reason: string | null
  coverage: number | null
}

/** One row per expert: accumulated evidence + the shadow weights that would apply to the next week. */
export function buildSummary(scores: ScoreRow[], weights: WeightRow[]): ExpertSummaryRow[] {
  const edges = scores.filter(r => r.metric === 'edge_regret' && r.position === 'ALL' && r.tier === 'ALL' && r.value != null)
  const cov = scores.filter(r => r.metric === 'coverage' && r.value != null)
  const rw = scores.filter(r => r.metric === 'rw_edge' && r.value != null)
  const next = latestWeekKey(weights)
  const at = (k: { season: number; week: number } | null, set: string) =>
    k ? weights.filter(w => w.season === k.season && w.week === k.week && w.weight_set === set) : []
  const six = at(next, 'six')
  const three = at(next, 'three')
  const prevKey = next ? latestWeekKey(weights.filter(w => w.season < next.season || (w.season === next.season && w.week < next.week))) : null
  const prev = at(prevKey, 'six')
  return expertsIn([...edges, ...six]).map(source => {
    const e = edges.filter(r => r.source === source).map(r => r.value as number)
    const w = six.find(x => x.source === source)
    const c = cov.filter(r => r.source === source).map(r => r.value as number)
    const s = sd(e)
    return {
      source,
      weeks: e.length,
      avgEdge: mean(e),
      edgeSe: s != null ? s / Math.sqrt(e.length) : null,
      avgRwEdge: mean(rw.filter(r => r.source === source).map(r => r.value as number)),
      skillMean: w?.skill_mean ?? null,
      skillSd: w?.skill_sd ?? null,
      pBetter: w?.p_better ?? null,
      weight: w?.weight ?? null,
      equalWeight: w?.equal_weight ?? null,
      prevWeight: prev.find(x => x.source === source)?.weight ?? null,
      threeWeight: three.find(x => x.source === source)?.weight ?? null,
      reason: w?.reason ?? null,
      coverage: mean(c),
    }
  })
}

/** Per expert: how many of their own top-ranked players per week were confirmed unavailable (late-news cost). */
export function buildUnavailable(scores: ScoreRow[]): { source: string; perWeek: number | null; weeks: number }[] {
  const rows = scores.filter(r => r.metric === 'top_unavailable' && r.value != null)
  return expertsIn(rows).map(source => {
    const v = rows.filter(r => r.source === source).map(r => r.value as number)
    return { source, perWeek: mean(v), weeks: v.length }
  })
}

export const POSITION_COMPONENTS = ['QB', 'RB', 'WR', 'TE', 'FLEX'] as const

/** Average per-component regret edge (points/week) by expert: where each expert gains or loses. */
export function buildPositionEdges(scores: ScoreRow[]): { source: string; byPos: Record<string, { mean: number; n: number } | null> }[] {
  const rows = scores.filter(r => r.metric === 'edge_regret' && r.tier === 'ALL' && r.value != null)
  return expertsIn(rows).map(source => ({
    source,
    byPos: Object.fromEntries(
      POSITION_COMPONENTS.map(p => {
        const v = rows.filter(r => r.source === source && r.position === p).map(r => r.value as number)
        return [p, v.length ? { mean: mean(v) as number, n: v.length } : null]
      }),
    ),
  }))
}

export const TIERS = ['T1', 'T2', 'T3', 'T4'] as const
export const TIER_LABELS: Record<string, string> = { T1: 'Top 1–6', T2: '7–12', T3: '13–24', T4: '25+' }

/** Pairwise start/sit accuracy by consensus tier (pooled over positions, pair-count weighted). */
export function buildTierAccuracy(scores: ScoreRow[]): { source: string; byTier: Record<string, { acc: number; pairs: number } | null> }[] {
  const rows = scores.filter(r => r.metric === 'pair_acc' && r.position === 'ALL' && r.value != null && (r.n ?? 0) > 0)
  return expertsIn(rows).map(source => ({
    source,
    byTier: Object.fromEntries(
      TIERS.map(t => {
        const rs = rows.filter(r => r.source === source && r.tier === t)
        const pairs = rs.reduce((a, r) => a + (r.n ?? 0), 0)
        const acc = pairs ? rs.reduce((a, r) => a + (r.value as number) * (r.n ?? 0), 0) / pairs : null
        return [t, acc == null ? null : { acc, pairs }]
      }),
    ),
  }))
}

export interface HistoryGrid {
  weeks: { season: number; week: number }[]
  sources: string[]
  value: (source: string, season: number, week: number) => number | null
}

function grid(rows: { season: number; week: number; source: string; v: number | null }[]): HistoryGrid {
  const keys = new Map<string, { season: number; week: number }>()
  rows.forEach(r => keys.set(`${r.season}-${r.week}`, { season: r.season, week: r.week }))
  const weeks = [...keys.values()].sort((a, b) => a.season - b.season || a.week - b.week)
  const map = new Map(rows.map(r => [`${r.source}|${r.season}|${r.week}`, r.v]))
  return { weeks, sources: expertsIn(rows), value: (s, season, week) => map.get(`${s}|${season}|${week}`) ?? null }
}

export const edgeHistory = (scores: ScoreRow[]): HistoryGrid =>
  grid(scores.filter(r => r.metric === 'edge_regret' && r.position === 'ALL' && r.tier === 'ALL').map(r => ({ season: r.season, week: r.week, source: r.source, v: r.value })))

export const weightHistory = (weights: WeightRow[], set: 'six' | 'three' = 'six'): HistoryGrid =>
  grid(weights.filter(w => w.weight_set === set).map(w => ({ season: w.season, week: w.week, source: w.source, v: w.weight })))

/** Plain-language confidence label from how much evidence exists and how far from the field. */
export function evidenceLabel(weeks: number, pBetter: number | null): string {
  if (weeks < 4) return 'Too early'
  if (pBetter == null) return '—'
  if (pBetter >= 0.85) return 'Likely above field'
  if (pBetter <= 0.15) return 'Likely below field'
  return 'Not distinguishable'
}

export interface ExpertEvalData {
  scores: ScoreRow[]
  weights: WeightRow[]
  backtest: BacktestRow | null
  loading: boolean
  error: string | null
}

const SCORE_METRICS = ['edge_regret', 'regret', 'pair_acc', 'pair_pts', 'rank_corr', 'coverage', 'n_imputed', 'top_unavailable', 'rw_edge']

export function useExpertEval(scoring: EvalScoring): ExpertEvalData {
  const [state, setState] = useState<ExpertEvalData>({ scores: [], weights: [], backtest: null, loading: true, error: null })
  useEffect(() => {
    let cancelled = false
    setState(s => ({ ...s, loading: true, error: null }))
    const order = (q: any, cols: string[]) => cols.reduce((acc, c) => acc.order(c, { ascending: true }), q)
    ;(async () => {
      const scoresP = fetchAllRows<ScoreRow>((from, to) =>
        order(supabase.from('expert_eval_scores').select('season,week,source,position,tier,metric,value,n')
          .eq('scoring', scoring).eq('config_version', EVAL_CONFIG_VERSION).in('metric', SCORE_METRICS), ['season', 'week', 'source', 'position', 'tier', 'metric']).range(from, to))
      const weightsP = fetchAllRows<WeightRow>((from, to) =>
        order(supabase.from('expert_eval_weights')
          .select('season,week,weight_set,source,weight,equal_weight,skill_mean,skill_sd,p_better,weeks_n,raw_mean,reason')
          .eq('scoring', scoring).eq('config_version', EVAL_CONFIG_VERSION).eq('position', 'ALL').eq('tier', 'ALL'), ['season', 'week', 'weight_set', 'source']).range(from, to))
      const btP = supabase.from('expert_eval_backtests').select('run_id,created_at,summary').eq('scoring', scoring)
        .eq('config_version', EVAL_CONFIG_VERSION).like('run_id', 'promo-%').order('created_at', { ascending: false }).limit(1)
      const [s, w, b] = await Promise.all([scoresP, weightsP, btP])
      if (cancelled) return
      const error = s.error?.message ?? w.error?.message ?? b.error?.message ?? null
      setState({ scores: s.data, weights: w.data, backtest: ((b.data ?? [])[0] as BacktestRow) ?? null, loading: false, error })
    })()
    return () => { cancelled = true }
  }, [scoring])
  return state
}
