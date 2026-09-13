import React from 'react'
import { useStore } from '../state/store'

export default function Header(){
  const ppr = useStore(s=>s.ppr)
  const set = useStore(s=>s.set)
  const stage = useStore(s=>s.seasonStage)
  return (
    <div className="header mb-4">
      <div>
        <h1 className="text-2xl font-semibold">Team Analyzer</h1>
        <div className="subtle">DS-anchored, lineup-aware trade value toolkit</div>
      </div>
      <div className="flex items-center gap-2">
        <span className="label">PPR</span>
        <select className="input" value={ppr} onChange={e=>set('ppr', e.target.value as any)}>
          <option value="1.0">1.0</option>
          <option value="0.5">0.5</option>
        </select>
        <span className="label">Season</span>
        <select className="input" value={stage} onChange={e=>set('seasonStage', e.target.value as any)}>
          <option value="early">Early</option>
          <option value="mid">Mid</option>
          <option value="late">Late</option>
        </select>
      </div>
    </div>
  )
}
