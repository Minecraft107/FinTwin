import { Play, Plus, RotateCw, Save, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { ScenarioChart } from '../charts/charts'
import {
  Button, Card, Disclaimer, EmptyState, Field, Input, Kpi, PageHeader, RiskBadge, Segmented, Select,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api, errorText } from '../services/api'
import { inr, monthLabel, pct, signed } from '../utils/format'

const TYPES = {
  large_purchase: 'Big purchase',
  income_change: 'Income change',
  expense_change: 'Spending change',
  sip_change: 'SIP change',
  new_loan: 'New loan',
  extra_savings: 'Save more each month',
  goal_delay: 'Delay a goal',
  one_time_income: 'One-time income (bonus)',
}
const DEFAULTS = {
  large_purchase: { amount: '', date: '', label: '', financed_by_loan: false, loan_rate: 12, loan_tenure_months: 24 },
  income_change: { mode: 'pct', value: '', start_date: '', duration_months: '' },
  expense_change: { mode: 'amount', value: '', kind: 'discretionary', start_date: '', duration_months: '' },
  sip_change: { amount: '', start_date: '' },
  new_loan: { principal: '', annual_rate: 10.5, tenure_months: 60, start_date: '', disbursed_to_cash: true },
  extra_savings: { amount: '', start_date: '' },
  goal_delay: { goal_id: '', months: 6 },
  one_time_income: { amount: '', date: '', label: '' },
}
const METRICS = [
  { value: 'cash', label: 'Cash' },
  { value: 'net_worth', label: 'Net worth' },
  { value: 'emergency_fund', label: 'Emergency fund' },
  { value: 'debt', label: 'Debt' },
  { value: 'investments', label: 'Investments' },
]

const num = (v) => (v === '' || v == null ? undefined : Number(v))
const opt = (v) => v || undefined

function toPayload(c) {
  switch (c.type) {
    case 'large_purchase':
      return { type: c.type, amount: num(c.amount), date: opt(c.date), label: opt(c.label), financed_by_loan: c.financed_by_loan,
        ...(c.financed_by_loan ? { loan_annual_rate: num(c.loan_rate) / 100, loan_tenure_months: num(c.loan_tenure_months) } : {}) }
    case 'income_change':
    case 'expense_change':
      return { type: c.type, [c.mode]: num(c.value), start_date: opt(c.start_date), duration_months: num(c.duration_months),
        ...(c.type === 'expense_change' ? { kind: c.kind } : {}) }
    case 'new_loan':
      return { type: c.type, principal: num(c.principal), annual_rate: num(c.annual_rate) / 100, tenure_months: num(c.tenure_months),
        start_date: opt(c.start_date), disbursed_to_cash: c.disbursed_to_cash }
    case 'goal_delay':
      return { type: c.type, goal_id: num(c.goal_id), months: num(c.months) }
    case 'one_time_income':
      return { type: c.type, amount: num(c.amount), date: opt(c.date), label: opt(c.label) }
    default:
      return { type: c.type, amount: num(c.amount), start_date: opt(c.start_date) }
  }
}

// Saved scenarios store API payloads; turn one back into form state.
function fromPayload(p) {
  const base = { ...DEFAULTS[p.type], type: p.type, key: crypto.randomUUID() }
  if (p.type === 'income_change' || p.type === 'expense_change') {
    return { ...base, mode: p.pct != null ? 'pct' : 'amount', value: p.pct ?? p.amount, start_date: p.start_date ?? '', duration_months: p.duration_months ?? '', kind: p.kind ?? base.kind }
  }
  if (p.type === 'new_loan') return { ...base, ...p, annual_rate: p.annual_rate * 100, start_date: p.start_date ?? '' }
  if (p.type === 'large_purchase') return { ...base, ...p, date: p.date ?? '', label: p.label ?? '', loan_rate: (p.loan_annual_rate ?? 0.12) * 100, loan_tenure_months: p.loan_tenure_months ?? 24 }
  return { ...base, ...Object.fromEntries(Object.entries(p).map(([k, v]) => [k, v ?? ''])) }
}

function ChangeEditor({ change, goals, onChange, onRemove }) {
  const set = (k) => (e) => onChange({ ...change, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const t = change.type
  const amountOrPct = (label) => (
    <>
      <Field label="Change by">
        <Select value={change.mode} onChange={set('mode')}><option value="pct">Percent</option><option value="amount">₹ per month</option></Select>
      </Field>
      <Field label={change.mode === 'pct' ? `${label} change (%)` : `${label} change (₹/month)`} hint="Negative to decrease">
        <Input type="number" required value={change.value} onChange={set('value')} />
      </Field>
      <Field label="From"><Input type="date" value={change.start_date} onChange={set('start_date')} /></Field>
      <Field label="For (months)" hint="Blank = permanent"><Input type="number" min="1" value={change.duration_months} onChange={set('duration_months')} /></Field>
    </>
  )
  return (
    <div className="rounded-lg border border-line p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold text-ink">{TYPES[t]}</span>
        <button type="button" className="rounded p-1 text-ink-3 hover:bg-slate-100" aria-label={`Remove ${TYPES[t]}`} onClick={onRemove}><X className="size-4" /></button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {t === 'large_purchase' && (
          <>
            <Field label="Amount (₹)"><Input type="number" min="1" required value={change.amount} onChange={set('amount')} /></Field>
            <Field label="When"><Input type="date" value={change.date} onChange={set('date')} /></Field>
            <Field label="What (optional)"><Input value={change.label} onChange={set('label')} placeholder="e.g. Laptop" /></Field>
            <label className="flex items-end gap-2 pb-2 text-sm text-ink-2"><input type="checkbox" checked={change.financed_by_loan} onChange={set('financed_by_loan')} /> Pay with a loan / EMI</label>
            {change.financed_by_loan && (
              <>
                <Field label="Loan rate (% a year)"><Input type="number" min="0" max="60" step="0.1" value={change.loan_rate} onChange={set('loan_rate')} /></Field>
                <Field label="Tenure (months)"><Input type="number" min="1" max="360" value={change.loan_tenure_months} onChange={set('loan_tenure_months')} /></Field>
              </>
            )}
          </>
        )}
        {t === 'income_change' && amountOrPct('Income')}
        {t === 'expense_change' && (
          <>
            {amountOrPct('Spending')}
            <Field label="Kind"><Select value={change.kind} onChange={set('kind')}><option value="discretionary">Discretionary</option><option value="essential">Essential</option></Select></Field>
          </>
        )}
        {(t === 'sip_change' || t === 'extra_savings') && (
          <>
            <Field label={t === 'sip_change' ? 'SIP change (₹/month)' : 'Save extra (₹/month)'} hint={t === 'sip_change' ? 'Negative to reduce' : 'By spending this much less'}>
              <Input type="number" required value={change.amount} onChange={set('amount')} />
            </Field>
            <Field label="From"><Input type="date" value={change.start_date} onChange={set('start_date')} /></Field>
          </>
        )}
        {t === 'new_loan' && (
          <>
            <Field label="Loan amount (₹)"><Input type="number" min="1" required value={change.principal} onChange={set('principal')} /></Field>
            <Field label="Rate (% a year)"><Input type="number" min="0" max="60" step="0.1" required value={change.annual_rate} onChange={set('annual_rate')} /></Field>
            <Field label="Tenure (months)"><Input type="number" min="1" max="360" required value={change.tenure_months} onChange={set('tenure_months')} /></Field>
            <Field label="Starts"><Input type="date" value={change.start_date} onChange={set('start_date')} /></Field>
            <label className="flex items-center gap-2 text-sm text-ink-2 sm:col-span-2"><input type="checkbox" checked={change.disbursed_to_cash} onChange={set('disbursed_to_cash')} /> The money comes into my account (untick if it's spent straight away, e.g. on a car)</label>
          </>
        )}
        {t === 'goal_delay' && (
          <>
            <Field label="Goal">
              <Select required value={change.goal_id} onChange={set('goal_id')}>
                <option value="">Choose a goal</option>
                {goals.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </Select>
            </Field>
            <Field label="Delay by (months)"><Input type="number" min="1" max="120" required value={change.months} onChange={set('months')} /></Field>
          </>
        )}
        {t === 'one_time_income' && (
          <>
            <Field label="Amount (₹)"><Input type="number" min="1" required value={change.amount} onChange={set('amount')} /></Field>
            <Field label="When"><Input type="date" value={change.date} onChange={set('date')} /></Field>
            <Field label="What (optional)"><Input value={change.label} onChange={set('label')} placeholder="e.g. Annual bonus" /></Field>
          </>
        )}
      </div>
    </div>
  )
}

function Results({ result, onSaved }) {
  const [metric, setMetric] = useState('cash')
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const i = result.impact
  const states = [
    ['Today', result.current_state],
    [`Without the change (${monthLabel(i.checkpoint_month)})`, result.baseline_state],
    [`With the change (${monthLabel(i.checkpoint_month)})`, result.simulated_state],
  ]
  const ROWS = [
    ['Cash balance', 'cash_balance', inr], ['Emergency fund', 'emergency_fund', inr], ['Investments', 'investments_value', inr],
    ['Loans outstanding', 'total_debt', inr], ['Net worth', 'net_worth', inr], ['Monthly surplus', 'net_cash_flow', inr],
    ['Savings ratio', 'savings_ratio', pct], ['Debt-to-income', 'debt_to_income', pct],
    ['Emergency cover', 'emergency_months', (v) => (v == null ? '—' : `${v.toFixed(1)} months`)],
    ['Health score', 'health_score', (v) => (v == null ? '—' : v.toFixed(0))],
  ]

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await api.post('/simulation/scenarios', { ...result.scenario, name })
      setName('')
      onSaved()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <RiskBadge level={result.risk_level} />
          <p className="text-sm font-medium text-ink">{result.recommendation}</p>
        </div>
        <p className="mt-3 text-sm text-ink-2">{result.explanation}</p>
        {result.risk_factors.length > 0 && (
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-2">{result.risk_factors.map((f) => <li key={f}>{f}</li>)}</ul>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Cash in 12 months" value={signed(i.cash_change)} hint="vs without the change" />
        <Kpi label="Net worth in 12 months" value={signed(i.net_worth_change)} />
        <Kpi label="Monthly surplus" value={signed(i.monthly_cash_flow_change)} />
        <Kpi label="Health score" value={i.health_score_change == null ? '—' : signed(i.health_score_change, (v) => v.toFixed(1))} hint={`${result.simulated_state.health_score?.toFixed(0) ?? '—'} vs ${result.baseline_state.health_score?.toFixed(0) ?? '—'}`} />
      </div>
      {(i.emergency_fund_drawn > 0 || i.first_shortfall_month) && (
        <Card>
          <p className="text-sm text-ink-2">
            Emergency fund used: <strong className="text-ink">{inr(i.emergency_fund_drawn)}</strong>
            {i.first_shortfall_month && <> · money runs out in <strong className="text-red-700">{monthLabel(i.first_shortfall_month)}</strong> (short by up to {inr(i.max_shortfall)})</>}
          </p>
        </Card>
      )}

      <Card title="Month by month" action={<Segmented label="Metric" options={METRICS} value={metric} onChange={setMetric} />}>
        <ScenarioChart timeline={result.timeline} metric={metric} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Current vs simulated state">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 font-medium" />{states.map(([label]) => <th key={label} className="pb-2 text-right font-medium">{label}</th>)}</tr></thead>
              <tbody className="divide-y divide-line">
                {ROWS.map(([label, key, fmt]) => (
                  <tr key={key}><td className="py-2 text-ink-2">{label}</td>{states.map(([l, s]) => <td key={l} className="tabular py-2 text-right">{fmt(s[key])}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="space-y-4">
          {result.goals.length > 0 && (
            <Card title="Goals">
              <ul className="space-y-2 text-sm">
                {result.goals.map((g) => (
                  <li key={g.goal_id} className="flex justify-between gap-3">
                    <span className="text-ink">{g.name}</span>
                    <span className="text-right text-ink-2">
                      {monthLabel(g.scenario_completion) || 'not at this pace'}
                      {g.scenario_completion_estimated && <span className="text-xs text-ink-3"> (est.)</span>}
                      {g.delay_months ? <span className={g.delay_months > 0 ? 'text-red-700' : 'text-green-700'}> · {Math.abs(g.delay_months)} mo {g.delay_months > 0 ? 'later' : 'sooner'}</span> : null}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          <Card title="Assumptions">
            <ul className="list-disc space-y-1 pl-5 text-xs text-ink-2">{result.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
            {result.notes.map((n) => <p key={n} className="mt-2 text-xs text-amber-800">{n}</p>)}
          </Card>
          <Card title="Save this scenario">
            <form onSubmit={save} className="flex gap-2">
              <Input required maxLength={120} placeholder="e.g. New laptop in January" value={name} onChange={(e) => setName(e.target.value)} aria-label="Scenario name" />
              <Button type="submit" loading={saving}><Save className="size-4" /> Save</Button>
            </form>
            {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
          </Card>
        </div>
      </div>
    </div>
  )
}

// Prefill from links such as /simulator?type=large_purchase&amount=130000
function changesFromQuery(params) {
  const type = params.get('type')
  if (!type || !DEFAULTS[type]) return []
  const c = { ...DEFAULTS[type], type, key: crypto.randomUUID() }
  if (params.get('pct')) Object.assign(c, { mode: 'pct', value: params.get('pct') })
  if (params.get('amount')) Object.assign(c, c.mode ? { mode: 'amount', value: params.get('amount') } : { amount: params.get('amount') })
  return [c]
}

export default function Simulator() {
  const [params] = useSearchParams()
  const [changes, setChanges] = useState(() => changesFromQuery(params))
  const [horizon, setHorizon] = useState(24)
  const [inflation, setInflation] = useState(0)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState('large_purchase')
  const goals = useApi('/goals')
  const saved = useApi('/simulation/scenarios')

  async function run(e) {
    e?.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post('/simulation/what-if', { changes: changes.map(toPayload), horizon_months: horizon, inflation_pct: Number(inflation) })
      setResult(data)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function rerun(id) {
    const { data } = await api.post(`/simulation/scenarios/${id}/run`)
    setChanges(data.result.scenario.changes.map(fromPayload))
    setHorizon(data.result.scenario.horizon_months)
    setResult(data.result)
    saved.reload()
  }

  async function remove(id) {
    await api.del(`/simulation/scenarios/${id}`)
    saved.reload()
  }

  return (
    <>
      <PageHeader
        title="What-If Simulator"
        description="Test a decision before you make it. A deterministic month-by-month model projects your finances with and without the change; nothing here is a guess by an AI."
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-4 xl:col-span-2">
          <Card title="Scenario">
            <form onSubmit={run} className="space-y-3">
              {changes.length === 0 && <p className="text-sm text-ink-2">Add one or more changes to simulate.</p>}
              {changes.map((c, idx) => (
                <ChangeEditor key={c.key} change={c} goals={goals.data ?? []}
                  onChange={(next) => setChanges(changes.map((x, j) => (j === idx ? next : x)))}
                  onRemove={() => setChanges(changes.filter((_, j) => j !== idx))} />
              ))}
              <div className="flex flex-wrap items-end gap-3 border-t border-line pt-4">
                <Field label="Add a change">
                  <Select value={adding} onChange={(e) => setAdding(e.target.value)}>
                    {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </Select>
                </Field>
                <Button variant="secondary" disabled={changes.length >= 10} onClick={() => setChanges([...changes, { ...DEFAULTS[adding], type: adding, key: crypto.randomUUID() }])}>
                  <Plus className="size-4" /> Add
                </Button>
                <Field label="Horizon">
                  <Select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
                    {[12, 24, 36, 60].map((h) => <option key={h} value={h}>{h} months</option>)}
                  </Select>
                </Field>
                <Field label="Inflation (% a year)"><Input type="number" min="0" max="20" step="0.5" value={inflation} onChange={(e) => setInflation(e.target.value)} className="w-28" /></Field>
                <Button type="submit" loading={busy} disabled={!changes.length} className="ml-auto"><Play className="size-4" /> Run simulation</Button>
              </div>
              {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
            </form>
          </Card>
          {result ? <Results result={result} onSaved={saved.reload} /> : <EmptyState title="Results appear here">Try “Big purchase” for ₹1,30,000, or a loan, a pay cut or a higher SIP.</EmptyState>}
        </div>
        <Card title="Saved scenarios" subtitle="Re-run against your latest data">
          {!saved.data?.length ? <p className="text-sm text-ink-2">None saved yet.</p> : (
            <ul className="divide-y divide-line">
              {saved.data.map((s) => (
                <li key={s.id} className="py-3 text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-medium text-ink">{s.name}</div>
                      {s.latest_result && <div className="mt-1 flex items-center gap-2"><RiskBadge level={s.latest_result.risk_level} /><span className="text-xs text-ink-3">{signed(s.latest_result.cash_change_12m)} cash</span></div>}
                    </div>
                    <div className="flex">
                      <button type="button" className="rounded p-1.5 text-ink-3 hover:bg-slate-100" aria-label={`Re-run ${s.name}`} onClick={() => rerun(s.id)}><RotateCw className="size-4" /></button>
                      <button type="button" className="rounded p-1.5 text-ink-3 hover:bg-red-50 hover:text-red-700" aria-label={`Delete ${s.name}`} onClick={() => remove(s.id)}><Trash2 className="size-4" /></button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Disclaimer>Simulations are estimates under the stated assumptions, not predictions or guarantees.</Disclaimer>
    </>
  )
}
