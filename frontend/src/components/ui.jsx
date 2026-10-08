import { AlertOctagon, AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { useEffect } from 'react'
import { errorText } from '../services/api'

export function Card({ title, subtitle, action, children, className = '' }) {
  return (
    <section className={`rounded-xl border border-line bg-white p-5 shadow-sm ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

const BUTTON = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-600/50',
  secondary: 'border border-line bg-white text-ink hover:bg-slate-50 disabled:text-ink-3',
  ghost: 'text-ink-2 hover:bg-slate-100',
  danger: 'border border-red-200 bg-white text-red-700 hover:bg-red-50',
}

export function Button({ variant = 'primary', loading, children, className = '', ...props }) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed ${BUTTON[variant]} ${className}`}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Field({ label, hint, error, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-ink-2">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-ink-3">{hint}</span>}
      {error && <span className="mt-1 block text-xs text-red-700">{error}</span>}
    </label>
  )
}

const CONTROL =
  'w-full rounded-lg border border-line bg-white px-3 py-2 text-sm text-ink outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100'

export const Input = (props) => <input {...props} className={`${CONTROL} ${props.className ?? ''}`} />
export const Select = ({ children, ...props }) => (
  <select {...props} className={`${CONTROL} ${props.className ?? ''}`}>
    {children}
  </select>
)

// Status colours are reserved for state and always come with an icon and a label.
const STATUS = {
  good: { cls: 'bg-green-50 text-green-800 ring-green-600/20', dot: 'bg-good', Icon: CheckCircle2 },
  info: { cls: 'bg-slate-100 text-slate-700 ring-slate-500/20', dot: 'bg-slate-400', Icon: Info },
  warning: { cls: 'bg-amber-50 text-amber-800 ring-amber-600/20', dot: 'bg-warning', Icon: AlertTriangle },
  serious: { cls: 'bg-orange-50 text-orange-800 ring-orange-600/20', dot: 'bg-serious', Icon: AlertTriangle },
  critical: { cls: 'bg-red-50 text-red-800 ring-red-600/20', dot: 'bg-critical', Icon: AlertOctagon },
}
const LEVEL_TONE = { LOW: 'info', MEDIUM: 'warning', HIGH: 'serious', CRITICAL: 'critical' }
const RISK_TONE = { LOW: 'good', MEDIUM: 'warning', HIGH: 'serious', CRITICAL: 'critical' }

export function StatusBadge({ tone = 'info', children }) {
  const { cls, Icon } = STATUS[tone]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>
      <Icon className="size-3.5" aria-hidden />
      {children}
    </span>
  )
}

// Alert severity (LOW is informational) vs. simulated risk level (LOW is good).
export const SeverityBadge = ({ level }) => <StatusBadge tone={LEVEL_TONE[level]}>{level}</StatusBadge>
export const RiskBadge = ({ level }) => <StatusBadge tone={RISK_TONE[level]}>{level} risk</StatusBadge>

const GOAL_TONE = {
  on_track: 'good', achieved: 'good', at_risk: 'warning', off_track: 'serious', overdue: 'critical',
  paused: 'info', no_target_date: 'info',
}
export const GoalStatusBadge = ({ status }) => (
  <StatusBadge tone={GOAL_TONE[status] ?? 'info'}>{status.replace(/_/g, ' ')}</StatusBadge>
)

export function SourceBadge({ source }) {
  if (!source) return null
  const text = { observed: 'from transactions', declared: 'from your profile', holdings: 'from loans/investments' }
  return <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-ink-3">{text[source] ?? source}</span>
}

// Stat tile: label, value, optional delta (colour = direction × whether up is good).
export function Kpi({ label, value, delta, deltaGood, hint, icon: Icon }) {
  const deltaCls = delta == null ? '' : deltaGood ? 'text-green-700' : 'text-red-700'
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between text-xs font-medium text-ink-3">
        <span>{label}</span>
        {Icon && <Icon className="size-4 text-ink-3" aria-hidden />}
      </div>
      <div className="mt-2 text-2xl font-semibold text-ink">{value}</div>
      {(delta != null || hint) && (
        <div className="mt-1 text-xs">
          {delta != null && <span className={`font-medium ${deltaCls}`}>{delta}</span>}
          {hint && <span className="text-ink-3"> {hint}</span>}
        </div>
      )}
    </div>
  )
}

// Meter: severity-coloured fill on a lighter track.
export function Meter({ value, max = 100, label }) {
  const ratio = Math.max(0, Math.min(1, (value ?? 0) / max))
  const fill = ratio >= 0.8 ? 'bg-good' : ratio > 0.5 ? 'bg-series-1' : ratio > 0.3 ? 'bg-warning' : 'bg-critical'
  return (
    <div className="h-2 w-full rounded-full bg-slate-100" role="meter" aria-valuenow={value} aria-valuemax={max} aria-label={label}>
      <div className={`h-2 rounded-full ${fill}`} style={{ width: `${ratio * 100}%` }} />
    </div>
  )
}

export function ScoreGauge({ score, grade, label, size = 132 }) {
  const r = size / 2 - 10
  const circumference = 2 * Math.PI * r
  const ratio = score == null ? 0 : score / 100
  const stroke = ratio >= 0.85 ? '#0ca30c' : ratio >= 0.7 ? '#2a78d6' : ratio >= 0.55 ? '#fab219' : ratio >= 0.4 ? '#ec835a' : '#d03b3b'
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef2f6" strokeWidth="10" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={stroke} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${circumference * ratio} ${circumference}`}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-4xl font-semibold text-ink">{score == null ? '—' : Math.round(score)}</div>
        <div className="text-xs text-ink-3">{grade ? `${grade} · ${label}` : 'of 100'}</div>
      </div>
    </div>
  )
}

export function PageHeader({ title, description, action }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-ink-2">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="flex items-center gap-2 py-10 text-sm text-ink-3" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800" role="alert">
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1">{errorText(error)}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }) {
  return (
    <div className="rounded-xl border border-dashed border-line bg-white px-6 py-10 text-center">
      <p className="font-medium text-ink">{title}</p>
      {children && <div className="mt-2 text-sm text-ink-2">{children}</div>}
    </div>
  )
}

export function Modal({ title, open, onClose, children, wide }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:items-center" onMouseDown={onClose}>
      <div
        role="dialog" aria-modal="true" aria-label={title}
        className={`w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} rounded-xl bg-white p-5 shadow-xl`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          <button type="button" onClick={onClose} className="rounded p-1 text-ink-3 hover:bg-slate-100" aria-label="Close">
            <X className="size-5" />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-line bg-white p-0.5">
      {options.map((o) => (
        <button
          key={o.value} type="button" onClick={() => onChange(o.value)} aria-pressed={value === o.value}
          className={`rounded-md px-2.5 py-1 text-xs font-medium ${value === o.value ? 'bg-brand-600 text-white' : 'text-ink-2 hover:bg-slate-100'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Disclaimer({ children }) {
  return (
    <p className="mt-6 text-xs text-ink-3">
      {children ??
        'FinTwin is a decision-support and educational tool, not a licensed financial advisor. Forecasts and simulations are estimates based on your data and stated assumptions.'}
    </p>
  )
}
