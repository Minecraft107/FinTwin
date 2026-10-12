import { AlertOctagon, AlertTriangle, CheckCircle2, Info, Loader2, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { errorText } from '../services/api'

export function Card({ title, subtitle, action, children, className = '', style }) {
  return (
    <section style={style} className={`rounded-xl border border-line bg-white p-6 ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-[15px] font-medium tracking-tight text-ink">{title}</h2>}
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
  primary: 'bg-ink text-white hover:bg-[#3a3835] disabled:bg-ink/40',
  secondary: 'border border-line bg-white text-ink hover:border-ink/20 hover:bg-slate-50 disabled:text-ink-3',
  ghost: 'text-ink-2 hover:bg-slate-100',
  danger: 'border border-red-200 bg-white text-red-700 hover:bg-red-50',
}

export function Button({ variant = 'primary', loading, children, className = '', ...props }) {
  return (
    <button
      type="button"
      {...props}
      disabled={props.disabled || loading}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition duration-200 ease-out-soft active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100 ${BUTTON[variant]} ${className}`}
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
  'w-full rounded-md border border-line bg-white px-3 py-2 text-sm text-ink outline-none transition duration-200 placeholder:text-ink-3 focus:border-ink/40 focus:ring-4 focus:ring-ink/5'

export const Input = (props) => <input {...props} className={`${CONTROL} ${props.className ?? ''}`} />
export const Select = ({ children, ...props }) => (
  <select {...props} className={`${CONTROL} ${props.className ?? ''}`}>
    {children}
  </select>
)

// Status colours are reserved for state and always come with an icon and a label.
const STATUS = {
  good: { cls: 'bg-green-50 text-green-800', dot: 'bg-good', Icon: CheckCircle2 },
  info: { cls: 'bg-slate-100 text-slate-700', dot: 'bg-slate-400', Icon: Info },
  warning: { cls: 'bg-amber-50 text-amber-800', dot: 'bg-warning', Icon: AlertTriangle },
  serious: { cls: 'bg-orange-50 text-orange-800', dot: 'bg-serious', Icon: AlertTriangle },
  critical: { cls: 'bg-red-50 text-red-800', dot: 'bg-critical', Icon: AlertOctagon },
}
const LEVEL_TONE = { LOW: 'info', MEDIUM: 'warning', HIGH: 'serious', CRITICAL: 'critical' }
const RISK_TONE = { LOW: 'good', MEDIUM: 'warning', HIGH: 'serious', CRITICAL: 'critical' }

export function StatusBadge({ tone = 'info', children }) {
  const { cls, Icon } = STATUS[tone]
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium tracking-[0.05em] uppercase ${cls}`}>
      <Icon className="size-3" aria-hidden />
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
  return <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-3">{text[source] ?? source}</span>
}

// Stat tile: label, value, optional delta (colour = direction × whether up is good).
export function Kpi({ label, value, delta, deltaGood, hint, icon: Icon }) {
  const deltaCls = delta == null ? '' : deltaGood ? 'text-green-700' : 'text-red-700'
  return (
    <div className="rounded-xl border border-line bg-white p-5">
      <div className="flex items-center justify-between text-xs text-ink-3">
        <span>{label}</span>
        {Icon && <Icon className="size-4 text-ink-3/70" strokeWidth={1.5} aria-hidden />}
      </div>
      <div className="tabular mt-3 text-[1.65rem] leading-none font-medium tracking-tight text-ink">{value}</div>
      {(delta != null || hint) && (
        <div className="mt-2 text-xs">
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
  const fill = ratio >= 0.8 ? 'bg-good' : ratio > 0.5 ? 'bg-ink/70' : ratio > 0.3 ? 'bg-warning' : 'bg-critical'
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100" role="meter" aria-valuenow={value} aria-valuemax={max} aria-label={label}>
      <div className={`h-full origin-left rounded-full ${fill}`} style={{ transform: `scaleX(${ratio})`, transition: 'transform 900ms var(--ease-out-soft)' }} />
    </div>
  )
}

export function ScoreGauge({ score, grade, label, size = 132 }) {
  const r = size / 2 - 10
  const circumference = 2 * Math.PI * r
  const ratio = score == null ? 0 : score / 100
  const stroke = ratio >= 0.7 ? 'var(--color-good)' : ratio >= 0.55 ? 'var(--color-warning)' : ratio >= 0.4 ? 'var(--color-serious)' : 'var(--color-critical)'
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-slate-100)" strokeWidth="6" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={stroke} strokeWidth="6" strokeLinecap="round"
          strokeDasharray={`${circumference * ratio} ${circumference}`}
        />
      </svg>
      <div className="absolute text-center">
        <div className="font-serif text-5xl leading-none tracking-tight text-ink">{score == null ? '—' : Math.round(score)}</div>
        <div className="mt-1.5 font-mono text-[11px] tracking-wide text-ink-3 uppercase">{grade ? `${grade} · ${label}` : 'of 100'}</div>
      </div>
    </div>
  )
}

export function PageHeader({ title, description, action }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-serif text-[2.25rem] leading-[1.1] tracking-[-0.02em] text-ink">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm text-ink-2">{description}</p>}
      </div>
      {action}
    </div>
  )
}

// Skeleton in the rough shape of a page (tiles and panels) instead of a bare spinner.
export function Loading({ label = 'Loading…' }) {
  return (
    <div role="status" aria-live="polite">
      <div className="flex items-center gap-2 pb-6 text-sm text-ink-3">
        <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
      </div>
      <div className="grid animate-pulse gap-4 lg:grid-cols-3" aria-hidden>
        <div className="h-72 rounded-xl bg-slate-100 lg:row-span-2" />
        <div className="grid grid-cols-2 gap-4 lg:col-span-2 xl:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="h-28 rounded-xl bg-slate-100" />)}
        </div>
        <div className="h-64 rounded-xl bg-slate-100 lg:col-span-2" />
      </div>
    </div>
  )
}

// Fades its children up once they scroll into view; CSS turns this off for reduced motion.
export function Reveal({ as: Tag = 'div', index = 0, className = '', children, ...props }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    if (typeof IntersectionObserver === 'undefined') {
      el.classList.add('is-visible')
      return undefined
    }
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        el.classList.add('is-visible')
        io.disconnect()
      }
    }, { rootMargin: '0px 0px -8% 0px' })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <Tag ref={ref} className={`reveal-on-scroll ${className}`} style={{ '--i': index }} {...props}>
      {children}
    </Tag>
  )
}

// A real product screenshot in a light browser frame. Images live in public/screens (captured
// from the seeded demo account at 1440x900, exported at 1600x1000).
export function ScreenFrame({ src, alt, label, eager = false, className = '' }) {
  return (
    <figure className={`rounded-2xl bg-ink/[0.03] p-1.5 ring-1 ring-line ${className}`}>
      <div className="overflow-hidden rounded-xl border border-line bg-white shadow-[0_30px_60px_-30px_rgba(31,30,28,0.28)]">
        <div className="flex items-center gap-1.5 border-b border-line px-3.5 py-2.5" aria-hidden>
          <span className="size-2 rounded-full bg-slate-100 ring-1 ring-line" />
          <span className="size-2 rounded-full bg-slate-100 ring-1 ring-line" />
          <span className="size-2 rounded-full bg-slate-100 ring-1 ring-line" />
          {label && <span className="ml-2.5 truncate font-mono text-[10.5px] text-ink-3">{label}</span>}
        </div>
        <img
          src={src}
          alt={alt}
          width={1600}
          height={1000}
          loading={eager ? 'eager' : 'lazy'}
          decoding="async"
          className="block h-auto w-full"
        />
      </div>
    </figure>
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
    <div className="rounded-xl border border-dashed border-ink/15 bg-surface px-6 py-12 text-center">
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
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/30 p-4 backdrop-blur-[2px] sm:items-center" onMouseDown={onClose}>
      <div
        role="dialog" aria-modal="true" aria-label={title}
        className={`w-full ${wide ? 'max-w-4xl' : 'max-w-lg'} rounded-xl border border-line bg-white p-6 shadow-[0_24px_48px_-12px_rgba(31,30,28,0.18)]`}
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
    <div role="group" aria-label={label} className="inline-flex rounded-md border border-line bg-white p-0.5">
      {options.map((o) => (
        <button
          key={o.value} type="button" onClick={() => onChange(o.value)} aria-pressed={value === o.value}
          className={`rounded px-2.5 py-1 text-xs font-medium transition duration-200 ${value === o.value ? 'bg-ink text-white' : 'text-ink-2 hover:bg-slate-100'}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Disclaimer({ children }) {
  return (
    <p className="mt-10 max-w-3xl border-t border-line pt-4 text-xs text-ink-3">
      {children ??
        'FinTwin is a decision-support and educational tool, not a licensed financial advisor. Forecasts and simulations are estimates based on your data and stated assumptions.'}
    </p>
  )
}
