// src/components/Sidebar.tsx
import Brand from './Brand'
import { NAV_ITEMS, type PageId } from '../nav'

interface SidebarProps {
  active: PageId
  onSelect: (id: PageId) => void
}

export default function Sidebar({ active, onSelect }: SidebarProps) {
  return (
    <aside
      className="hidden md:flex md:flex-col md:w-48 md:shrink-0 md:h-screen md:sticky md:top-0 px-3 py-4 gap-1 border-r"
      style={{ background: 'var(--bg-sidebar)', borderColor: 'var(--bg-card-border)' }}
    >
      <div className="px-3 pb-4">
        <Brand />
      </div>
      {NAV_ITEMS.map(item => (
        <button
          key={item.id}
          className={`nav-item ${active === item.id ? 'nav-item-active' : ''}`}
          onClick={() => onSelect(item.id)}
        >
          {item.label}
        </button>
      ))}
    </aside>
  )
}
