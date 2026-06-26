import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/pricing-sandbox', label: 'Pricing Sandbox' },
  { to: '/contracts', label: 'Contracts' },
  { to: '/contract-explorer', label: 'Contract Explorer' },
  { to: '/rules', label: 'Rules' },
  { to: '/claim-simulation', label: 'Claim Simulation' },
  { to: '/reprice-claim', label: 'Reprice Claim' },
  { to: '/batch-reprice', label: 'Batch Reprice' },
  { to: '/providers', label: 'Providers' },
  { to: '/members', label: 'Members' },
  { to: '/products', label: 'Products' },
  { to: '/rule-simulator', label: 'Rule Simulator' },
  { to: '/run-scenario', label: 'Run Scenario' },
  { to: '/batch-monitor', label: 'Batch Monitor' },
  { to: '/admin', label: 'Admin' },
]

interface SidebarProps {
  isOpen: boolean
  onClose?: () => void
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `block rounded px-3 py-2 text-sm font-medium ${
      isActive ? 'bg-primary-50 text-primary-700' : 'text-slate-700 hover:bg-slate-100'
    }`

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/20 lg:hidden"
          aria-hidden
          onClick={onClose}
        />
      )}
      <aside
        className={`
          fixed left-0 top-14 z-30 h-[calc(100vh-3.5rem)] w-56 border-r border-slate-200 bg-white transition-transform lg:translate-x-0
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <nav className="flex flex-col gap-1 p-3">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClass} onClick={onClose}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
    </>
  )
}
