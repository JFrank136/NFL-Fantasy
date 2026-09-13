import React, { useMemo, useState } from 'react'
import { useStore } from '../state/store'
import type { BlendedRow } from '../types'

export default function TradeSandbox(){
  const s = useStore()
  const rows = s.blendedByWeek[s.activeWeek||0] || []
  const [a, setA] = useState<string>('')
  const [b, setB] = useState<string>('')

  const parseList = (txt:string) => txt.split(/\n|,/).map(x=>x.trim()).filter(Boolean).map(x=>x.toLowerCase())
  const aNames = useMemo(()=> parseList(a), [a])
  const bNames = useMemo(()=> parseList(b), [b])
  const find = (n:string) => rows.find(r=> r.name.toLowerCase()===n)

  const listA = aNames.map(find).filter(Boolean) as BlendedRow[]
  const listB = bNames.map(find).filter(Boolean) as BlendedRow[]

  const sum = (ls:BlendedRow[]) => ls.reduce((s,c)=> s + (c.blended || 0), 0)

  const totalA = sum(listA), totalB = sum(listB)
  const delta = Math.round(totalB - totalA)

  const benchWeight = s.benchWeight
  const narrative = delta >= 0 ? 'Improves starting lineup potential' : 'Risks starting lineup value'
  const summary = `${delta>=0?'+':''}${delta} blended (raw). ${narrative}. Consider bench impact with ${Math.round(benchWeight*100)}% weight.`

  return (
    <div className="card p-4">
      <div className="text-lg font-semibold mb-2">Trade Sandbox (beta)</div>
      <div className="grid md:grid-cols-2 gap-3">
        <div>
          <div className="label mb-1">Side A (you give)</div>
          <textarea className="input w-full h-24" placeholder="Comma or line-separated names" value={a} onChange={e=>setA(e.target.value)} />
        </div>
        <div>
          <div className="label mb-1">Side B (you get)</div>
          <textarea className="input w-full h-24" placeholder="Comma or line-separated names" value={b} onChange={e=>setB(e.target.value)} />
        </div>
      </div>
      <div className="mt-3 grid md:grid-cols-3 gap-3">
        <div className="card p-3"><div className="subtle">Side A total</div><div className="text-2xl font-semibold">{Math.round(totalA)}</div></div>
        <div className="card p-3"><div className="subtle">Side B total</div><div className="text-2xl font-semibold">{Math.round(totalB)}</div></div>
        <div className="card p-3"><div className="subtle">Net (B - A)</div><div className="text-2xl font-semibold">{delta>=0?'+':''}{delta}</div></div>
      </div>
      <div className="mt-3">
        <div className="label">Summary</div>
        <div className="mt-1 badge">{summary}</div>
      </div>
    </div>
  )
}
