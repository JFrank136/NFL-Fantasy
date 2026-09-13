import React, { useMemo } from 'react'
import { useStore } from '../state/store'
import { computeDeltaByPlayer } from '../lib/trends'

export default function TrendsView(){
  const s = useStore()
  const weeks = s.weeks
  const active = s.activeWeek
  if (!active) return null
  const curr = s.blendedByWeek[active] || []
  const prevWeek = weeks.filter(w=> w < active).slice(-1)[0]
  const prev = prevWeek ? (s.blendedByWeek[prevWeek]||[]) : []
  const deltas = useMemo(()=> computeDeltaByPlayer(curr, prev), [curr, prev])

  const topRisers = deltas.filter(d=> (d.delta ?? -999) > 0).sort((a,b)=> (b.delta??0)-(a.delta??0)).slice(0,20)
  const topFallers = deltas.filter(d=> (d.delta ?? 999) < 0).sort((a,b)=> (a.delta??0)-(b.delta??0)).slice(0,20)

  return (
    <div className="card p-4">
      <div className="text-lg font-semibold mb-2">Trends (Δ vs prev week)</div>
      {!prevWeek && <div className="subtle">Need at least 2 weeks loaded</div>}
      {prevWeek && (
        <div className="grid md:grid-cols-2 gap-4">
          <div>
            <div className="mb-2 font-medium">Top Risers</div>
            <table className="table">
              <thead><tr><th>Name</th><th>Pos</th><th>Δ</th></tr></thead>
              <tbody>
                {topRisers.map(r=> (<tr key={r.playerId}><td>{r.name}</td><td>{r.pos}</td><td className="text-right">+{r.delta}</td></tr>))}
              </tbody>
            </table>
          </div>
          <div>
            <div className="mb-2 font-medium">Top Fallers</div>
            <table className="table">
              <thead><tr><th>Name</th><th>Pos</th><th>Δ</th></tr></thead>
              <tbody>
                {topFallers.map(r=> (<tr key={r.playerId}><td>{r.name}</td><td>{r.pos}</td><td className="text-right">{r.delta}</td></tr>))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
