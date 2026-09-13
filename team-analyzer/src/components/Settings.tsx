import React from 'react'
import { useStore } from '../state/store'

export default function Settings(){
  const s = useStore()
  return (
    <div className="card p-4">
      <div className="text-lg font-semibold mb-3">Settings</div>
      <div className="grid md:grid-cols-3 gap-3">
        <div>
          <div className="label mb-1">Blend Weights</div>
          <div className="flex items-center gap-2">
            <span>DS</span>
            <input className="input w-20" type="number" value={Math.round(s.dsWeight*100)} onChange={e=>s.set('dsWeight', Math.max(0, Math.min(1, Number(e.target.value)/100)))} />
            <span>Boone</span>
            <input className="input w-20" type="number" value={Math.round(s.booneWeight*100)} onChange={e=>s.set('booneWeight', Math.max(0, Math.min(1, Number(e.target.value)/100)))} />
          </div>
          <div className="subtle mt-1">Default DS 60% / Boone 40%</div>
        </div>
        <div>
          <div className="label mb-1">Bench Weight</div>
          <input className="input w-24" type="number" value={Math.round(s.benchWeight*100)} onChange={e=>s.set('benchWeight', Math.max(0, Math.min(1, Number(e.target.value)/100)))} />
          <div className="subtle">Early/Mid/Late affects this baseline</div>
        </div>
        <div>
          <div className="label mb-1">Elite Premium (VORP eq.)</div>
          <input className="input w-24" type="number" value={s.elitePremium} onChange={e=>s.set('elitePremium', Number(e.target.value))} />
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <label className="flex items-center gap-2"><input type="checkbox" checked={s.showStacking} onChange={e=>s.set('showStacking', e.target.checked)} /> Prefer stacking (small)</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={s.byePenalty} onChange={e=>s.set('byePenalty', e.target.checked)} /> Bye-week penalty</label>
        <label className="flex items-center gap-2">
          Handcuff Policy
          <select className="input" value={s.handcuffPolicy} onChange={e=>s.set('handcuffPolicy', e.target.value as any)}>
            <option value="neutral">Neutral</option>
            <option value="own">Prefer own handcuff</option>
            <option value="others">Prefer others' handcuff</option>
          </select>
        </label>
      </div>
    </div>
  )
}
