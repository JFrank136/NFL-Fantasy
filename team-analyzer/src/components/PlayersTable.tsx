import React, { useMemo, useState } from 'react'
import { useStore } from '../state/store'
import type { BlendedRow } from '../types'

export default function PlayersTable(){
  const activeWeek = useStore(s=>s.activeWeek)
  const rows = useStore(s=> s.blendedByWeek[s.activeWeek||0] || [])
  const [query, setQuery] = useState('')
  const [pos, setPos] = useState('ALL')
  const [mode, setMode] = useState<'blended'|'ds'|'boone'>('blended')
  const [sortKey, setSortKey] = useState<'blended'|'dsRaw'|'booneRaw'|'delta'>('blended')
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('desc')

  const display = useMemo(()=>{
    let list = rows as (BlendedRow & {delta?: number})[]
    if (query) list = list.filter(r => r.name.toLowerCase().includes(query.toLowerCase()))
    if (pos!=='ALL') list = list.filter(r => (r.pos||'') === pos)
    list = list.slice().sort((a,b)=>{
      const A = (sortKey==='blended'? a.blended : sortKey==='dsRaw'? a.dsRaw : sortKey==='booneRaw'? a.booneRaw : (a as any).delta)?.valueOf() ?? -Infinity
      const B = (sortKey==='blended'? b.blended : sortKey==='dsRaw'? b.dsRaw : sortKey==='booneRaw'? b.booneRaw : (b as any).delta)?.valueOf() ?? -Infinity
      return (sortDir==='desc' ? (B as number)-(A as number) : (A as number)-(B as number))
    })
    return list
  }, [rows, query, pos, sortKey, sortDir])

  if (!activeWeek) return null

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <input className="input" placeholder="Search players..." value={query} onChange={e=>setQuery(e.target.value)} />
        <select className="input" value={pos} onChange={e=>setPos(e.target.value)}>
          {['ALL','QB','RB','WR','TE'].map(p=> <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="input" value={mode} onChange={e=>setMode(e.target.value as any)}>
          <option value="blended">Blended</option>
          <option value="ds">DraftSharks (raw)</option>
          <option value="boone">Boone (raw)</option>
        </select>
        <select className="input" value={sortKey} onChange={e=>setSortKey(e.target.value as any)}>
          <option value="blended">Sort by Blended</option>
          <option value="dsRaw">Sort by DS</option>
          <option value="booneRaw">Sort by Boone</option>
        </select>
        <button className="btn" onClick={()=>setSortDir(d => d==='asc'?'desc':'asc')}>{sortDir==='asc'?'Asc':'Desc'}</button>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>Team</th>
            <th>Pos</th>
            <th>DS</th>
            <th>Boone′</th>
            <th>Blended</th>
          </tr>
        </thead>
        <tbody>
          {display.map((r,i)=> (
            <tr key={r.playerId}>
              <td>{i+1}</td>
              <td>{r.name}</td>
              <td>{r.team||''}</td>
              <td>{r.pos||''}</td>
              <td className="text-right">{r.dsRaw ?? ''}</td>
              <td className="text-right">{r.booneOnDsScale != null ? Math.round(r.booneOnDsScale) : ''}</td>
              <td className="text-right font-semibold">{r.blended ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
