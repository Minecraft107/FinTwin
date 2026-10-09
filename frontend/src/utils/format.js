const rupees = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })

export const inr = (value) => (value == null || Number.isNaN(value) ? '—' : rupees.format(value))

// Compact Indian notation for axes and tiles: ₹950, ₹45K, ₹1.3L, ₹2.4Cr.
export function inrCompact(value) {
  if (value == null) return '—'
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : ''
  const fmt = (n, unit) => `${sign}₹${(+n.toFixed(n >= 10 ? 0 : 1)).toString()}${unit}`
  if (abs >= 1e7) return fmt(abs / 1e7, 'Cr')
  if (abs >= 1e5) return fmt(abs / 1e5, 'L')
  if (abs >= 1e3) return fmt(abs / 1e3, 'K')
  return `${sign}₹${Math.round(abs)}`
}

export const pct = (ratio, digits = 1) => (ratio == null ? '—' : `${(ratio * 100).toFixed(digits)}%`)

export const signed = (value, formatter = inr) => (value > 0 ? `+${formatter(value)}` : formatter(value))

const monthFmt = new Intl.DateTimeFormat('en-IN', { month: 'short', year: '2-digit' })
const dateFmt = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })

// "2026-09" or "2026-09-30" -> "Sep 26"
export const monthLabel = (iso) => (iso ? monthFmt.format(new Date(`${iso.slice(0, 7)}-01T00:00:00`)) : '')
export const dateLabel = (iso) => (iso ? dateFmt.format(new Date(`${iso.slice(0, 10)}T00:00:00`)) : '')

// Local date, not UTC: toISOString() gives yesterday in India between 00:00 and 05:30.
export const today = (now = new Date()) =>
  `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

export const titleCase = (s) => (s ? s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()) : '')

const ASSET_LABELS = {
  sip_equity: 'SIP (equity)', mutual_fund: 'Mutual fund', stocks: 'Stocks', fd: 'Fixed deposit',
  ppf: 'PPF', gold: 'Gold', other: 'Other',
}
export const assetLabel = (type) => ASSET_LABELS[type] ?? titleCase(type)
