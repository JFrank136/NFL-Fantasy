// src/components/MobileNav.tsx
import { useState } from 'react'
import Brand from './Brand'
import { NAV_ITEMS, type PageId } from '../nav'

interface MobileNavProps {
  active: PageId
  onSelect: (id: PageId) => void
}

export default function MobileNav({ active, onSelect }: MobileNavProps) {
  const [open, setOpen] = useState(false)

  return (
    <div className="md:hidden">
      <div
        className="flex items-center justify-between px-4 py-3 border-b"
        style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--bg-card-border)' }}
      >
        <Brand />
        <button
          aria-label={open ? 'Close menu' : 'Open menu'}
          className="text-2xl leading-none"
          style={{ color: 'var(--text-primary)' }}
          onClick={() => setOpen(o => !o)}
        >
          ☰
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-40" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <div
            className="absolute top-0 left-0 bottom-0 w-64 p-4 flex flex-col gap-1"
            style={{ background: 'var(--bg-sidebar)' }}
          >
            <div className="px-3 pb-4">
              <Brand />
            </div>
            {NAV_ITEMS.map(item => (
              <button
                key={item.id}
                className={`nav-item ${active === item.id ? 'nav-item-active' : ''}`}
                onClick={() => {
                  onSelect(item.id)
                  setOpen(false)
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
