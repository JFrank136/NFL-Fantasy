export type PPR = '0.5' | '1.0'
export type SourceId = 'draftsharks' | 'boone'
export type PlayerId = string // name|pos|team (canonical)

export interface SourceRow {
  name: string
  pos?: string
  team?: string
  ppr: PPR
  week: number
  rawValue: number | null
  source: SourceId
}

export interface BlendedRow {
  playerId: PlayerId
  name: string
  pos?: string
  team?: string
  week: number
  ppr: PPR
  dsRaw?: number | null
  booneRaw?: number | null
  booneOnDsScale?: number | null
  blended?: number | null
  vorp?: number
}

export interface LeagueSettings {
  name: string
  teams: number
  ppr: PPR
  slots: {
    QB: number
    RB: number
    WR: number
    TE: number
    FLEX: number
  }
  bench: number
  ir: number
  superflex?: boolean
}

export interface TeamProfile {
  id: string
  leagueId?: string
  teamId?: string
  name: string
  league: LeagueSettings
  roster: string[]
}

export interface TrendPoint {
  week: number
  value: number | null
}

export interface TrendDelta {
  playerId: PlayerId
  name: string
  pos?: string
  team?: string
  delta: number | null
}
