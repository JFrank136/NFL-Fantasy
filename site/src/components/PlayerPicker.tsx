import { useMemo, useState } from 'react'

export interface PickablePlayer {
  key: string
  playerName: string
  position: string
  team: string | null
  blended: number | null
}

/** Shared search-and-add player box (Player Comparison now; Start/Sit and
 * Add/Drop later). Candidates should already exclude players already chosen. */
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

  const matches = useMemo(() => {
    if (query.trim().length < 2) return []
    const q = query.toLowerCase()
    return candidates.filter(p => p.playerName.toLowerCase().includes(q)).slice(0, 8)
  }, [candidates, query])

  return (
    <div className="space-y-1">
      <input
        className="input w-full"
        placeholder={placeholder}
        value={query}
        disabled={disabled}
        onChange={e => setQuery(e.target.value)}
      />
      {!disabled && matches.length > 0 && (
        <div className="card p-1 space-y-0.5">
          {matches.map(p => (
            <div
              key={p.key}
              className="px-2 py-1.5 rounded-lg cursor-pointer flex items-center justify-between text-sm"
              onMouseDown={() => { onAdd(p); setQuery('') }}
            >
              <span>{p.playerName} <span className="subtle">{p.position}{p.team ? ` · ${p.team}` : ''}</span></span>
              <span className="subtle">{p.blended != null ? Math.round(p.blended) : '—'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
