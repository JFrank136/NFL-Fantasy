import React, { useEffect, useMemo } from 'react'
import { useStore } from '../state/store'
import { robustLinearFit, applyScale } from '../lib/regression'
import type { BlendedRow, SourceRow } from '../types'
import { tidyName, canonicalKey } from '../lib/names'

export default function BlendEngine(){
  const { rowsByWeek, activeWeek, dsWeight, booneWeight, set } = useStore(s=>({ rowsByWeek: s.rowsByWeek, activeWeek: s.activeWeek, dsWeight: s.dsWeight, booneWeight: s.booneWeight, set: s.set }))

  const blended = useMemo(() => {
    if (!activeWeek) return []
    const rows = rowsByWeek[activeWeek] || []
    const ds = rows.filter(r=>r.source==='draftsharks' && r.rawValue!=null)
    const boone = rows.filter(r=>r.source==='boone' && r.rawValue!=null)
    // Create name maps
    const key = (r: SourceRow) => canonicalKey(tidyName(r.name), r.pos, r.team)
    const dsMap = new Map(ds.map(r=>[key(r), r]))
    const booneMap = new Map(boone.map(r=>[key(r), r]))
    // Fit scale using intersection
    const inter: {x:number,y:number}[] = []
    dsMap.forEach((d, k) => {
      const b = booneMap.get(k)
      if (b && Number.isFinite(d.rawValue!) && Number.isFinite(b.rawValue!)) {
        inter.push({ x: b.rawValue as number, y: d.rawValue as number })
      }
    })
    const xs = inter.map(p=>p.x), ys = inter.map(p=>p.y)
    const { a, b } = robustLinearFit(xs, ys)
    // Union players
    const nameKeys = new Set<string>([...dsMap.keys(), ...booneMap.keys()])
    const out: BlendedRow[] = []
    nameKeys.forEach(k => {
      const d = dsMap.get(k)
      const bRow = booneMap.get(k)
      const booneOnDs = bRow?.rawValue != null ? applyScale(a,b,bRow.rawValue) : null
      const blendDen = (d?.rawValue != null ? dsWeight : 0) + (booneOnDs != null ? booneWeight : 0) || 1
      const blended = ((d?.rawValue ?? 0) * (d?.rawValue != null ? dsWeight : 0) + (booneOnDs ?? 0) * (booneOnDs != null ? booneWeight : 0)) / blendDen
      out.push({
        playerId: k,
        name: tidyName(d?.name || bRow?.name || ''),
        pos: (d?.pos || bRow?.pos),
        team: (d?.team || bRow?.team),
        week: activeWeek!,
        ppr: (d?.ppr || bRow?.ppr || '1.0') as any,
        dsRaw: d?.rawValue ?? null,
        booneRaw: bRow?.rawValue ?? null,
        booneOnDsScale: booneOnDs,
        blended: Math.round(blended)
      })
    })
    return out.sort((a,b)=> (b.blended??-1) - (a.blended??-1))
  }, [rowsByWeek, activeWeek, dsWeight, booneWeight])

  useEffect(()=>{
    if (useStore.getState().activeWeek) useStore.getState().set('blendedByWeek', { ...useStore.getState().blendedByWeek, [useStore.getState().activeWeek!]: blended } as any)
  }, [blended])

  return null
}
