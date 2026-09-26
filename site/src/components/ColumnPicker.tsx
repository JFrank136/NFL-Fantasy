import { useState } from 'react'

export interface PickableColumn {
  key: string
  label: string
}

/** "Columns" button that expands into on/off chips. For wide tables on a
 * phone, where scrolling sideways past columns you don't care about is the
 * annoying part. Hidden state lives in the caller so it survives tab flips. */
export default function ColumnPicker({
  columns,
  hidden,
  onToggle,
}: {
  columns: PickableColumn[]
  hidden: Set<string>
  onToggle: (key: string) => void
}) {
  const [open, setOpen] = useState(false)
  const hiddenCount = columns.filter(c => hidden.has(c.key)).length

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <button className={`btn ${open ? 'btn-primary' : ''}`} onClick={() => setOpen(o => !o)} aria-expanded={open}>
        Columns{hiddenCount > 0 ? ` (${hiddenCount} hidden)` : ''}
      </button>
      {open && columns.map(c => (
        <button
          key={c.key}
          className={`btn ${!hidden.has(c.key) ? 'btn-primary' : ''}`}
          onClick={() => onToggle(c.key)}
          title={hidden.has(c.key) ? 'Hidden -- click to show' : 'Shown -- click to hide'}
        >
          {c.label}
        </button>
      ))}
    </div>
  )
}

export function toggleInSet(prev: Set<string>, key: string): Set<string> {
  const next = new Set(prev)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  return next
}
