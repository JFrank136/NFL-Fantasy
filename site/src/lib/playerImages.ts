// src/lib/playerImages.ts
//
// Headshot lookup: identityKey(canonical_name, position) -> ESPN athlete id,
// from the Supabase `player_images` table (built by scripts/build_player_images.py
// from ESPN rosters). Fetched once per page load and shared by every avatar.
// Missing players just have no entry and the avatar shows initials.

import { useEffect, useState } from 'react'
import { fetchAllRows, supabase } from './supabase'
import { identityKey } from './blend'

const HEADSHOT_BASE = 'https://a.espncdn.com/i/headshots/nfl/players/full'

const LOGO_BASE = 'https://a.espncdn.com/i/teamlogos/nfl/500'

/** ids prefixed "team:" are defenses -> ESPN team logo; others are athlete headshots. */
export const isLogoId = (espnId: string) => espnId.startsWith('team:')
export const headshotUrl = (espnId: string) =>
  isLogoId(espnId) ? `${LOGO_BASE}/${espnId.slice(5)}.png` : `${HEADSHOT_BASE}/${espnId}.png`

export const initials = (name: string) =>
  name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0]).join('')

let cache: Promise<Map<string, string>> | null = null

function loadImageMap(): Promise<Map<string, string>> {
  if (!cache) {
    cache = fetchAllRows<{ canonical_name: string; position: string; espn_id: string }>((from, to) =>
      supabase.from('player_images').select('canonical_name,position,espn_id').order('canonical_name').order('position').range(from, to),
    ).then(({ data, error }) => {
      if (error) {
        console.error('Failed to load player images:', error)
        cache = null // allow a retry on next mount
        return new Map()
      }
      return new Map(data.map(r => [identityKey(r.canonical_name, r.position), r.espn_id]))
    })
  }
  return cache
}

export function usePlayerImages(): Map<string, string> | null {
  const [map, setMap] = useState<Map<string, string> | null>(null)
  useEffect(() => {
    let cancelled = false
    loadImageMap().then(m => { if (!cancelled) setMap(m) })
    return () => { cancelled = true }
  }, [])
  return map
}
