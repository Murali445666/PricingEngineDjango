import { useState } from 'react'

const env = import.meta.env.MODE === 'production' ? 'Prod' : 'Dev'

export function Header({ onMenuClick }: { onMenuClick?: () => void }) {
  const [userOpen, setUserOpen] = useState(false)
  return (
    <header className="fixed top-0 left-0 right-0 z-40 flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 shadow-sm">
      <div className="flex items-center gap-3">
        {onMenuClick && (
          <button
            type="button"
            onClick={onMenuClick}
            className="rounded p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700 lg:hidden"
            aria-label="Toggle menu"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        )}
        <span className="text-lg font-semibold text-slate-900">Matrix Pricing Platform</span>
        <span
          className={`rounded border px-2 py-0.5 text-xs font-medium ${
            env === 'Prod' ? 'border-green-200 bg-green-50 text-green-700' : 'border-amber-200 bg-amber-50 text-amber-700'
          }`}
        >
          {env}
        </span>
      </div>
      <div className="relative">
        <button
          type="button"
          onClick={() => setUserOpen((o) => !o)}
          className="flex items-center gap-2 rounded border border-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-50"
        >
          <span className="text-slate-500">User</span>
          <svg className="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {userOpen && (
          <>
            <div className="fixed inset-0 z-10" aria-hidden onClick={() => setUserOpen(false)} />
            <div className="absolute right-0 top-full z-20 mt-1 w-48 rounded border border-slate-200 bg-white py-1 shadow-lg">
              <div className="px-3 py-2 text-sm text-slate-500">Placeholder user menu</div>
            </div>
          </>
        )}
      </div>
    </header>
  )
}
