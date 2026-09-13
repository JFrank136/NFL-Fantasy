import React, { useMemo, useRef, useState } from 'react'
import { useStore } from '../state/store'
import { parseCsvFile } from '../lib/csv'
import { detectWeekFromName, detectSourceFromName } from '../lib/weeks'
import { mapBoone, mapDraftSharks } from '../lib/sources'
import type { PPR, SourceRow } from '../types'

export default function WeekManager(){
  const ppr = useStore(s=>s.ppr)
  const set = useStore(s=>s.set)
  const weeks = useStore(s=>s.weeks)
  const rowsByWeek = useStore(s=>s.rowsByWeek)
  const [report, setReport] = useState<string>('')
  const dirInputRef = useRef<HTMLInputElement>(null)

  const onFiles = async (files: FileList) => {
    const newRows: Record<number, SourceRow[]> = {}
    let notes: string[] = []
    for (const file of Array.from(files)) {
      const week = detectWeekFromName(file.name) ?? 0
      const src = detectSourceFromName(file.name)
      const parsed = await parseCsvFile(file)
      const mapped: SourceRow[] = []
      for (const r of parsed) {
        if (src === 'boone') mapped.push(mapBoone(r, ppr as PPR, week))
        else if (src === 'draftsharks') mapped.push(mapDraftSharks(r, ppr as PPR, week))
      }
      newRows[week] = (newRows[week] || []).concat(mapped)
      notes.push(`${file.name}: ${mapped.length} rows → week ${week} (${src||'unknown'})`)
    }
    const merged = { ...rowsByWeek }
    Object.entries(newRows).forEach(([wk, rows])=>{
      merged[Number(wk)] = (merged[Number(wk)]||[]).concat(rows)
    })
    const wkList = Array.from(new Set(Object.keys(merged).map(n=>Number(n)))).sort((a,b)=>a-b)
    set('rowsByWeek', merged as any)
    set('weeks', wkList as any)
    if (!useStore.getState().activeWeek && wkList.length) set('activeWeek', wkList[wkList.length-1] as any)
    setReport(notes.join('\n'))
  }

  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-lg font-semibold">Weeks</div>
          <div className="subtle">Drag a folder or choose files — we auto-detect week & source</div>
        </div>
        <div className="flex items-center gap-2">
          <input ref={dirInputRef} type="file" multiple /* @ts-ignore */ webkitdirectory="true" className="hidden" onChange={e=> e.target.files && onFiles(e.target.files)} />
          <button className="btn" onClick={()=>dirInputRef.current?.click()}>Upload Folder</button>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <span className="label">Active Week</span>
        <select className="input" value={useStore.getState().activeWeek||''} onChange={e=>useStore.getState().set('activeWeek', Number(e.target.value) as any)}>
          {weeks.map(w=> <option key={w} value={w}>{w}</option>)}
        </select>
      </div>
      {report && <pre className="mt-3 text-xs whitespace-pre-wrap bg-neutral-950 p-2 rounded">{report}</pre>}
    </div>
  )
}
