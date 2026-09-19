import type { ReactNode } from 'react'
import type { Highlight } from '../lib/playerComparison'

export interface ComparisonColumn {
  key: string
  header: ReactNode
  subheader?: ReactNode
}

export interface ComparisonTableRow {
  id: string
  label: string
  cells: { text: string; highlight: Highlight }[]
}

/** Shared side-by-side table: one row per stat, one column per item, with
 * best/worst cells highlighted per row. Reused by Player Comparison and,
 * later, Start/Sit and Add/Drop. */
export default function ComparisonTable({
  columns,
  rows,
}: {
  columns: ComparisonColumn[]
  rows: ComparisonTableRow[]
}) {
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th />
            {columns.map(c => (
              <th key={c.key} className="text-right" style={{ textTransform: 'none' }}>
                <div style={{ color: 'var(--text-primary)' }} className="font-semibold text-sm">{c.header}</div>
                {c.subheader && <div>{c.subheader}</div>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td className="subtle">{r.label}</td>
              {r.cells.map((cell, i) => (
                <td
                  key={columns[i].key}
                  className={`text-right ${cell.highlight === 'best' ? 'cell-best' : cell.highlight === 'worst' ? 'cell-worst' : ''}`}
                >
                  {cell.text}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
