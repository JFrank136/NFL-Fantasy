// src/App.tsx
import React, { useState } from 'react'
import Header from './components/Header'
import BlendEngine from './components/BlendEngine'

// Using your barrel file at src/pages/index.ts
import { Rankings, TradeValues, Players, Trends, Roster, Trade, Weeks, Settings } from './pages'

type Tab = 'rankings' | 'tradevalues' | 'players' | 'trends' | 'roster' | 'trade' | 'weeks' | 'settings'
const TABS: Tab[] = ['rankings', 'tradevalues', 'players', 'trends', 'roster', 'trade', 'weeks', 'settings']
const TAB_LABELS: Record<Tab, string> = {
  rankings: 'Rankings',
  tradevalues: 'Trade Values',
  players: 'Players',
  trends: 'Trends',
  roster: 'Roster',
  trade: 'Trade',
  weeks: 'Weeks',
  settings: 'Settings',
}

export default function App() {
  const [tab, setTab] = useState<Tab>('rankings')

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-4">
      <Header />
      <BlendEngine />

      <div className="tabs">
        {TABS.map(t => (
          <button
            key={t}
            className={`tab ${tab === t ? 'tab-active' : ''}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {tab === 'rankings' && <Rankings />}
      {tab === 'tradevalues' && <TradeValues />}
      {tab === 'players' && <Players />}
      {tab === 'trends' && <Trends />}
      {tab === 'roster' && <Roster />}
      {tab === 'trade' && <Trade />}
      {tab === 'weeks' && <Weeks />}
      {tab === 'settings' && <Settings />}
    </div>
  )
}
