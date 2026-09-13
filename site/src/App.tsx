// src/App.tsx
import React, { useState } from 'react'
import Header from './components/Header'
import BlendEngine from './components/BlendEngine'

// Using your barrel file at src/pages/index.ts
import { Players, Trends, Roster, Trade, Weeks, Settings } from './pages'

type Tab = 'players' | 'trends' | 'roster' | 'trade' | 'weeks' | 'settings'
const TABS: Tab[] = ['players', 'trends', 'roster', 'trade', 'weeks', 'settings']

export default function App() {
  const [tab, setTab] = useState<Tab>('players')

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
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'players' && <Players />}
      {tab === 'trends' && <Trends />}
      {tab === 'roster' && <Roster />}
      {tab === 'trade' && <Trade />}
      {tab === 'weeks' && <Weeks />}
      {tab === 'settings' && <Settings />}
    </div>
  )
}
