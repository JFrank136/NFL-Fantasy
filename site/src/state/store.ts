import { create } from 'zustand'
import { immer } from 'zustand/middleware/immer'
import type { PPR, SourceRow, BlendedRow, LeagueSettings, TeamProfile } from '../types'

export interface AppState {
  ppr: PPR
  seasonStage: 'early' | 'mid' | 'late'
  benchWeight: number
  dsWeight: number
  booneWeight: number
  sources: Record<string, boolean>
  weeks: number[]
  activeWeek: number | null
  rowsByWeek: Record<number, SourceRow[]>
  blendedByWeek: Record<number, BlendedRow[]>
  league?: LeagueSettings
  teams: TeamProfile[]
  activeTeamId?: string
  showStacking: boolean
  handcuffPolicy: 'neutral' | 'own' | 'others'
  byePenalty: boolean
  elitePremium: number
  aliasMap: Record<string, string>
  includeKDST: boolean
  set<K extends keyof AppState>(k: K, v: AppState[K]): void
}

export const useStore = create<AppState>()(
  immer((set, get) => ({
    ppr: '1.0',
    seasonStage: 'early',
    benchWeight: 0.7,
    dsWeight: 0.6,
    booneWeight: 0.4,
    sources: { draftsharks: true, boone: true },
    weeks: [],
    activeWeek: null,
    rowsByWeek: {},
    blendedByWeek: {},
    league: {
      name: 'Default',
      teams: 10,
      ppr: '1.0',
      slots: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1 },
      bench: 6,
      ir: 1,
      superflex: false,
    },
    teams: [],
    activeTeamId: undefined,
    showStacking: false,
    handcuffPolicy: 'neutral',
    byePenalty: false,
    elitePremium: 8,
    aliasMap: {},
    includeKDST: false,
    set: <K extends keyof AppState>(k: K, v: AppState[K]) => {
      set((s: any) => {
        (s as AppState)[k] = v as any
      })
    },
  }))
)
