// src/nav.ts
//
// Single source of truth for site navigation, consumed by both Sidebar
// (desktop) and MobileNav (mobile drawer). Adding a future roadmap page
// (Data Health, Start/Sit, etc.) is a one-line addition here.

export type PageId = 'rankings' | 'tradevalues' | 'trade'

export interface NavItem {
  id: PageId
  label: string
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'rankings', label: 'Rankings' },
  { id: 'tradevalues', label: 'Trade Values' },
  { id: 'trade', label: 'Trade Analyzer' },
]
