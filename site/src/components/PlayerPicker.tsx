import { useMemo, useState } from 'react'

export interface PickablePlayer {
  key: string
  playerName: string
  position: string
  team: string | null
  blended: number | null
  /** When defined (even null), shown instead of `blended` in the dropdown row. */
  detail?: string | null
}

/** Shared search-and-add player box (Player Comparison, Start/Sit, Add/Drop)
 * -- same floating-popover styling and focus/blur behavior as Trade
 * Analyzer's picker, so every page's player search looks and behaves the
 * same. Candidates should already exclude players already chosen. */
export default function PlayerPicker({
  candidates,
  disabled = false,
  placeholder = 'Add a player…',
  onAdd,
}: {
  candidates: PickablePlayer[]
  disabled?: boolean
  placeholder?: string
  onAdd: (player: PickablePlayer) => void
}) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)

  const searching = query.trim().length >= 2
  const matches = useMemo(() => {
    if (!searching) return []
    const q = query.trim().toLowerCase()
    return candidates.filter(p => p.playerName.toLowerCase().includes(q)).slice(0, 8)
  }, [candidates, query, searching])

  return (
    <div className="relative">
      <input
        className="input w-full"
        placeholder={placeholder}
        value={query}
        disabled={disabled}
        onChange={e => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
      {!disabled && focused && searching && (
        <div className="search-results">
          {matches.length === 0 && <div className="px-3 py-2 text-sm">No matching players.</div>}
          {matches.map(p => (
            <div
              key={p.key}
              className="search-result"
              onMouseDown={() => { onAdd(p); setQuery('') }}
            >
              <span>{p.playerName} <span className="search-result-sub">{p.position}{p.team ? ` · ${p.team}` : ''}</span></span>
              <span className="search-result-meta">{p.detail !== undefined ? (p.detail ?? '—') : p.blended != null ? Math.round(p.blended) : '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
