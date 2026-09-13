import React, { useMemo, useState } from 'react'
import { useStore } from '../state/store'
import type { BlendedRow } from '../types'
import { computeVorp } from '../lib/vorp'

export default function RosterAnalyzer(){
  const s = useStore()
  const rows = s.blendedByWeek[s.activeWeek||0] || []
  const [rosterText, setRosterText] = useState('')
  const rosterNames = useMemo(()=> rosterText.split(/\n|,/).map(x=>x.trim()).filter(Boolean), [rosterText])

  const league = s.league!

  const starters = useMemo(()=>{
    const byPos = (pos:string) => rows.filter(r=> (r.pos||'').toUpperCase()===pos)
    const pick = (list:BlendedRow[], n:number) => list.slice(0,n).map(r=>r.playerId)
    const qb = pick(byPos('QB'), league.slots.QB)
    const rb = pick(byPos('RB'), league.slots.RB)
    const wr = pick(byPos('WR'), league.slots.WR)
    const te = pick(byPos('TE'), league.slots.TE)
    const used = new Set([...qb,...rb,...wr,...te])
    const flexPool = rows.filter(r=>['RB','WR','TE'].includes((r.pos||'')) && !used.has(r.playerId))
    const flex = pick(flexPool, league.slots.FLEX)
    return new Set([...qb,...rb,...wr,...te,...flex])
  }, [rows, league])

  const myRows = useMemo(()=>{
    if (!rosterNames.length) return []
    const low = new Set(rosterNames.map(n=>n.toLowerCase()))
    return rows.filter(r=> low.has(r.name.toLowerCase()))
  }, [rows, rosterNames])

  const { rows: withVorp } = useMemo(()=> computeVorp(rows, league), [rows, league])

  const total = myRows.reduce((s,c)=> s + (c.blended || 0), 0)
  const starterTotal = myRows.filter(r=> starters.has(r.playerId)).reduce((s,c)=> s + (c.blended || 0), 0)

  return (
    <div className="card p-4">
      <div className="text-lg font-semibold mb-2">Roster Analyzer</div>
      <textarea className="input w-full h-24" placeholder="Paste your roster names (comma or line separated)"
        value={rosterText} onChange={e=>setRosterText(e.target.value)} />
      <div className="mt-3 grid md:grid-cols-3 gap-3">
        <div className="card p-3">
          <div className="subtle">Team Score</div>
          <div className="text-2xl font-semibold">{Math.round(total)}</div>
        </div>
        <div className="card p-3">
          <div className="subtle">Starters (est.)</div>
          <div className="text-2xl font-semibold">{Math.round(starterTotal)}</div>
        </div>
        <div className="card p-3">
          <div className="subtle">Players Matched</div>
          <div className="text-2xl font-semibold">{myRows.length}</div>
        </div>
      </div>
      <div className="mt-4">
        <table className="table">
          <thead><tr><th>Name</th><th>Pos</th><th>Team</th><th>Blended</th><th>Starter?</th></tr></thead>
          <tbody>
            {myRows.map(r=> (
              <tr key={r.playerId}>
                <td>{r.name}</td>
                <td>{r.pos}</td>
                <td>{r.team||''}</td>
                <td className="text-right">{r.blended ?? ''}</td>
                <td>{starters.has(r.playerId)? 'Yes' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
