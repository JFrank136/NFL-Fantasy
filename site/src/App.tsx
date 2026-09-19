// src/App.tsx
import { useState } from 'react'
import Sidebar from './components/Sidebar'
import MobileNav from './components/MobileNav'
import { Rankings, TradeValues, TradeAnalyzer, MoversFallers, ExpertDisagreement, PlayerComparison } from './pages'
import type { PageId } from './nav'

export default function App() {
  const [page, setPage] = useState<PageId>('rankings')

  return (
    <div className="md:flex min-h-screen">
      <Sidebar active={page} onSelect={setPage} />
      <div className="flex-1 flex flex-col">
        <MobileNav active={page} onSelect={setPage} />
        <main className="flex-1 max-w-6xl w-full mx-auto p-4 space-y-4">
          {page === 'rankings' && <Rankings />}
          {page === 'tradevalues' && <TradeValues />}
          {page === 'trade' && <TradeAnalyzer />}
          {page === 'movers' && <MoversFallers />}
          {page === 'disagreement' && <ExpertDisagreement />}
          {page === 'compare' && <PlayerComparison />}
        </main>
      </div>
    </div>
  )
}
