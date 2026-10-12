import {
  ArrowLeftRight,
  BarChart3,
  Bot,
  Gauge,
  LayoutDashboard,
  LogOut,
  Menu,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
  User,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import ErrorBoundary from '../components/ErrorBoundary'
import { useAuth } from '../context/AuthContext'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/twin', label: 'Digital Twin', icon: Gauge },
  { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
  { to: '/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/forecasts', label: 'Forecasts', icon: TrendingUp },
  { to: '/goals', label: 'Goals', icon: Target },
  { to: '/simulator', label: 'What-If Simulator', icon: Sparkles },
  { to: '/risks', label: 'Risks & Alerts', icon: ShieldAlert },
  { to: '/coach', label: 'AI Coach', icon: Bot },
  { to: '/profile', label: 'Profile & Settings', icon: User },
]

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="grid size-8 place-items-center rounded-md bg-ink font-serif text-lg leading-none text-white">F</div>
      <div>
        <div className="text-sm font-medium tracking-tight text-ink">FinTwin</div>
        <div className="font-mono text-[10.5px] text-ink-3">Financial health twin</div>
      </div>
    </div>
  )
}

function NavItems({ onNavigate }) {
  return (
    <nav className="mt-8 space-y-0.5" aria-label="Main">
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition duration-200 ${
              isActive
                ? 'bg-white font-medium text-ink shadow-[0_0_0_1px_var(--color-line)]'
                : 'text-ink-2 hover:bg-white/70 hover:text-ink'
            }`
          }
        >
          <Icon className="size-4" strokeWidth={1.5} aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  )
}

export default function AppShell() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const footer = (
    <div className="border-t border-line pt-3">
      <div className="truncate px-3 text-sm font-medium text-ink">{user?.full_name}</div>
      <div className="truncate px-3 text-xs text-ink-3">{user?.email}</div>
      <button type="button" onClick={logout} className="mt-2 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-ink-2 transition duration-200 hover:bg-white/70 hover:text-ink">
        <LogOut className="size-4" strokeWidth={1.5} aria-hidden /> Log out
      </button>
    </div>
  )
  return (
    <div className="min-h-[100dvh] lg:pl-64">
      <a href="#main" className="sr-only z-50 rounded-md bg-ink px-3 py-2 text-sm text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3">
        Skip to content
      </a>
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col justify-between border-r border-line bg-surface px-4 py-5 lg:flex">
        <div>
          <Brand />
          <NavItems />
        </div>
        {footer}
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-page/85 px-4 py-3 backdrop-blur-md lg:hidden">
        <Brand />
        <button type="button" onClick={() => setOpen(true)} className="rounded-lg p-2 hover:bg-slate-100" aria-label="Open menu">
          <Menu className="size-5" />
        </button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 bg-slate-900/30 lg:hidden" onClick={() => setOpen(false)}>
          <div className="flex h-full w-72 flex-col justify-between bg-surface p-4" onClick={(e) => e.stopPropagation()}>
            <div>
              <div className="flex items-center justify-between">
                <Brand />
                <button type="button" onClick={() => setOpen(false)} className="rounded p-1 hover:bg-slate-100" aria-label="Close menu">
                  <X className="size-5" />
                </button>
              </div>
              <NavItems onNavigate={() => setOpen(false)} />
            </div>
            {footer}
          </div>
        </div>
      )}

      <main id="main" className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-10 lg:py-12">
        <ErrorBoundary key={pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>
    </div>
  )
}
