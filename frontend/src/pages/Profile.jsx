import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, ErrorState, Field, Input, Loading, Modal, PageHeader, Select, StatusBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useApi } from '../hooks/useApi'
import { api, errorText } from '../services/api'
import { assetLabel, inr, pct, titleCase } from '../utils/format'

const MONEY_FIELDS = [
  ['declared_monthly_income', 'Monthly take-home income (₹)', 'Used until you have a full month of transactions.'],
  ['monthly_essential_expenses', 'Essential expenses / month (₹)', 'Rent, groceries, bills, transport…'],
  ['monthly_discretionary_expenses', 'Discretionary expenses / month (₹)', 'Dining, shopping, entertainment…'],
  ['emergency_fund', 'Emergency fund (₹)', 'Money set aside only for emergencies.'],
  ['opening_balance', 'Bank balance (₹)', 'Your balance at the start of the date below.'],
]

function ProfileSection() {
  const profile = useApi('/financial-profile')
  if (profile.error) return <ErrorState error={profile.error} onRetry={profile.reload} />
  if (!profile.data) return <Loading />
  return <ProfileForm initial={profile.data} />
}

function ProfileForm({ initial }) {
  const [form, setForm] = useState(initial)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => { setSaved(false); setForm({ ...form, [k]: e.target.value }) }

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const body = { ...form, dependents: Number(form.dependents) }
      MONEY_FIELDS.forEach(([k]) => { body[k] = Number(form[k] || 0) })
      await api.put('/financial-profile', body)
      setSaved(true)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      {MONEY_FIELDS.map(([k, label, hint]) => (
        <Field key={k} label={label} hint={hint}><Input type="number" min="0" value={form[k]} onChange={set(k)} /></Field>
      ))}
      <Field label="Balance as of"><Input type="date" value={form.opening_balance_date} onChange={set('opening_balance_date')} /></Field>
      <Field label="Risk tolerance">
        <Select value={form.risk_tolerance} onChange={set('risk_tolerance')}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></Select>
      </Field>
      <Field label="Employment">
        <Select value={form.employment_type} onChange={set('employment_type')}>
          <option value="salaried">Salaried</option><option value="self_employed">Self-employed</option><option value="student">Student</option><option value="other">Other</option>
        </Select>
      </Field>
      <Field label="Dependents"><Input type="number" min="0" max="20" value={form.dependents} onChange={set('dependents')} /></Field>
      {error && <p className="text-sm text-red-700 sm:col-span-2" role="alert">{error}</p>}
      <div className="flex items-center justify-end gap-3 sm:col-span-2">
        {saved && <StatusBadge tone="good">Saved — your twin was recalculated</StatusBadge>}
        <Button type="submit" loading={busy}>Save profile</Button>
      </div>
    </form>
  )
}

const HOLDINGS = {
  investments: {
    title: 'Investments', empty: { name: '', asset_type: 'sip_equity', invested_amount: 0, current_value: 0, monthly_contribution: 0, expected_annual_return: 10 },
    fields: [['name', 'Name', 'text'], ['asset_type', 'Type', ['sip_equity', 'mutual_fund', 'stocks', 'fd', 'ppf', 'gold', 'other']], ['invested_amount', 'Invested (₹)', 'number'],
      ['current_value', 'Current value (₹)', 'number'], ['monthly_contribution', 'Monthly contribution (₹)', 'number'], ['expected_annual_return', 'Expected return (% a year)', 'number']],
    percent: ['expected_annual_return'],
    summary: (i) => `${assetLabel(i.asset_type)} · ${inr(i.current_value)} · ${inr(i.monthly_contribution)}/month · ${pct(i.expected_annual_return)} expected`,
  },
  loans: {
    title: 'Loans', empty: { name: '', loan_type: 'personal', principal: '', outstanding: '', annual_interest_rate: 10, emi: '', tenure_months: 60, start_date: '' },
    fields: [['name', 'Name', 'text'], ['loan_type', 'Type', ['home', 'car', 'personal', 'education', 'credit_card', 'other']], ['principal', 'Loan amount (₹)', 'number'],
      ['outstanding', 'Outstanding (₹)', 'number', 'Blank = loan amount'], ['annual_interest_rate', 'Interest rate (% a year)', 'number'], ['emi', 'EMI (₹)', 'number', 'Blank = calculated'],
      ['tenure_months', 'Tenure (months)', 'number'], ['start_date', 'Start date', 'date']],
    percent: ['annual_interest_rate'],
    summary: (l) => `EMI ${inr(l.emi)} · ${inr(l.outstanding)} of ${inr(l.principal)} outstanding · ${pct(l.annual_interest_rate)}`,
  },
}

function HoldingForm({ kind, initial, onSaved, onCancel }) {
  const spec = HOLDINGS[kind]
  const [form, setForm] = useState(() => {
    const base = initial ?? spec.empty
    return { ...base, ...Object.fromEntries(spec.percent.map((k) => [k, initial ? +(base[k] * 100).toFixed(2) : base[k]])) }
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    const body = {}
    for (const [k, , type] of spec.fields) {
      const v = form[k]
      if (type === 'number') { if (v !== '' && v != null) body[k] = spec.percent.includes(k) ? Number(v) / 100 : Number(v) } else body[k] = v
    }
    try {
      if (initial?.id) await api.put(`/${kind}/${initial.id}`, body)
      else await api.post(`/${kind}`, body)
      onSaved()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      {spec.fields.map(([k, label, type, hint]) => (
        <Field key={k} label={label} hint={hint}>
          {Array.isArray(type) ? (
            <Select value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })}>{type.map((o) => <option key={o} value={o}>{titleCase(o)}</option>)}</Select>
          ) : (
            <Input type={type} required={!hint && k !== 'invested_amount'} min={type === 'number' ? 0 : undefined} step="any" value={form[k] ?? ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
          )}
        </Field>
      ))}
      {error && <p className="text-sm text-red-700 sm:col-span-2" role="alert">{error}</p>}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={busy}>Save</Button>
      </div>
    </form>
  )
}

function Holdings({ kind }) {
  const spec = HOLDINGS[kind]
  const list = useApi(`/${kind}`)
  const [editing, setEditing] = useState(null)
  async function remove(item) {
    if (!window.confirm(`Delete "${item.name}"?`)) return
    await api.del(`/${kind}/${item.id}`)
    list.reload()
  }
  return (
    <Card title={spec.title} action={<Button variant="secondary" onClick={() => setEditing({})}><Plus className="size-4" /> Add</Button>}>
      {!list.data?.length ? <p className="text-sm text-ink-2">None recorded.</p> : (
        <ul className="divide-y divide-line">
          {list.data.map((item) => (
            <li key={item.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
              <div className="min-w-0"><div className="font-medium text-ink">{item.name}</div><div className="text-xs text-ink-3">{spec.summary(item)}</div></div>
              <div className="flex">
                <button type="button" className="rounded p-1.5 text-ink-3 hover:bg-slate-100" aria-label={`Edit ${item.name}`} onClick={() => setEditing(item)}><Pencil className="size-4" /></button>
                <button type="button" className="rounded p-1.5 text-ink-3 hover:bg-red-50 hover:text-red-700" aria-label={`Delete ${item.name}`} onClick={() => remove(item)}><Trash2 className="size-4" /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
      <Modal title={`${editing?.id ? 'Edit' : 'Add'} ${spec.title.toLowerCase().replace(/s$/, '')}`} open={editing != null} onClose={() => setEditing(null)}>
        {editing && <HoldingForm kind={kind} initial={editing.id ? editing : null} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); list.reload() }} />}
      </Modal>
    </Card>
  )
}

function ModelStatus() {
  const status = useApi('/ml/status')
  if (!status.data) return null
  const f = status.data.metrics.forecaster?.total_level
  const c = status.data.metrics.categorizer?.cascade
  const a = status.data.metrics.anomaly?.transaction_level?.['production (MEDIUM+ alerts)']
  return (
    <Card title="Machine-learning models" subtitle="Trained offline on a synthetic population; see docs/ml.md for the evaluation.">
      <ul className="space-y-2 text-sm">
        {Object.entries(status.data.artifacts).map(([name, info]) => (
          <li key={name} className="flex items-center justify-between">
            <span className="text-ink">{titleCase(name)}</span>
            <StatusBadge tone={info.available ? 'good' : 'warning'}>{info.available ? 'loaded' : 'not trained — using fallback'}</StatusBadge>
          </li>
        ))}
      </ul>
      {(f || c || a) && (
        <dl className="mt-4 grid gap-2 text-xs text-ink-2">
          {f?.xgboost && <div>Forecaster (held-out users): MAE {inr(f.xgboost.mae)}, R² {f.xgboost.r2.toFixed(2)} vs best baseline {inr(Math.min(...Object.entries(f).filter(([k]) => !['xgboost', 'per_user_selection'].includes(k)).map(([, v]) => v.mae)))}</div>}
          {c && <div>Categorizer on unseen merchants: {pct(c.overall_accuracy)} accuracy</div>}
          {a && <div>Anomaly detection: precision {a.precision.toFixed(2)}, recall {a.recall.toFixed(2)}</div>}
        </dl>
      )}
    </Card>
  )
}

export default function Profile() {
  const { user, logout } = useAuth()
  return (
    <>
      <PageHeader title="Profile & settings" description="These facts complete your Digital Twin. Saving any of them recalculates the twin, your health score and your alerts." />
      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Financial profile" className="xl:col-span-2"><ProfileSection /></Card>
        <div className="space-y-4">
          <Card title="Account">
            <p className="text-sm text-ink">{user.full_name}</p>
            <p className="text-sm text-ink-3">{user.email}</p>
            <Button variant="secondary" className="mt-4" onClick={logout}>Log out</Button>
          </Card>
          <ModelStatus />
        </div>
        <Holdings kind="investments" />
        <Holdings kind="loans" />
      </div>
    </>
  )
}
