import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import {
  Button, Card, Disclaimer, EmptyState, ErrorState, Field, GoalStatusBadge, Input, Loading, Meter, Modal,
  PageHeader, Segmented, Select,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api, errorText } from '../services/api'
import { inr, monthLabel } from '../utils/format'

const RETURNS = [{ value: 0, label: '0%' }, { value: 0.04, label: '4%' }, { value: 0.07, label: '7%' }, { value: 0.1, label: '10%' }]

function GoalForm({ initial, onSaved, onCancel }) {
  const [form, setForm] = useState(initial ?? { name: '', target_amount: '', current_amount: 0, target_date: '', priority: 3, monthly_contribution: 0, status: 'active' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    const body = {
      name: form.name, target_amount: Number(form.target_amount), current_amount: Number(form.current_amount || 0),
      target_date: form.target_date || null, priority: Number(form.priority),
      monthly_contribution: Number(form.monthly_contribution || 0), status: form.status,
    }
    try {
      if (initial?.id) await api.put(`/goals/${initial.id}`, body)
      else await api.post('/goals', body)
      onSaved()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2"><Field label="Goal"><Input required maxLength={120} value={form.name} onChange={set('name')} placeholder="e.g. Buy a car" /></Field></div>
      <Field label="Target amount (₹)"><Input type="number" min="1" required value={form.target_amount} onChange={set('target_amount')} /></Field>
      <Field label="Saved so far (₹)"><Input type="number" min="0" value={form.current_amount} onChange={set('current_amount')} /></Field>
      <Field label="Target date" hint="Optional"><Input type="date" value={form.target_date ?? ''} onChange={set('target_date')} /></Field>
      <Field label="Planned saving per month (₹)"><Input type="number" min="0" value={form.monthly_contribution} onChange={set('monthly_contribution')} /></Field>
      <Field label="Priority" hint="1 is funded first">
        <Select value={form.priority} onChange={set('priority')}>{[1, 2, 3, 4, 5].map((p) => <option key={p} value={p}>{p}</option>)}</Select>
      </Field>
      <Field label="Status">
        <Select value={form.status} onChange={set('status')}>
          <option value="active">Active</option><option value="paused">Paused</option><option value="achieved">Achieved</option>
        </Select>
      </Field>
      {error && <p className="text-sm text-red-700 sm:col-span-2" role="alert">{error}</p>}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={busy}>{initial?.id ? 'Save goal' : 'Add goal'}</Button>
      </div>
    </form>
  )
}

function TryChanges({ plan, annualReturn }) {
  const [form, setForm] = useState({ monthly_contribution: plan.planned_monthly, target_date: plan.target_date ?? '', extra_monthly_surplus: 0 })
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const body = { annual_return: annualReturn, monthly_contribution: Number(form.monthly_contribution), extra_monthly_surplus: Number(form.extra_monthly_surplus || 0) }
      if (form.target_date) body.target_date = form.target_date
      setResult((await api.post(`/goals/${plan.goal_id}/simulate`, body)).data)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-4 rounded-lg bg-slate-50 p-4">
      <h3 className="text-sm font-semibold text-ink">Try a change</h3>
      <form onSubmit={run} className="mt-3 grid gap-3 sm:grid-cols-4">
        <Field label="Save per month (₹)"><Input type="number" min="0" value={form.monthly_contribution} onChange={(e) => setForm({ ...form, monthly_contribution: e.target.value })} /></Field>
        <Field label="Target date"><Input type="date" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></Field>
        <Field label="Spending cut / month (₹)"><Input type="number" min="0" value={form.extra_monthly_surplus} onChange={(e) => setForm({ ...form, extra_monthly_surplus: e.target.value })} /></Field>
        <div className="flex items-end"><Button type="submit" loading={busy} className="w-full">See the effect</Button></div>
      </form>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {result && (
        <div className="mt-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <GoalStatusBadge status={result.current.status} /><span className="text-ink-3">→</span><GoalStatusBadge status={result.simulated.status} />
            <span className="text-ink-2">Reached {monthLabel(result.simulated.completion_at_fundable) || 'never at this pace'} (was {monthLabel(result.current.completion_at_fundable) || 'never'})</span>
          </div>
          <p className="mt-2 text-ink-2">{result.simulated.explanation}</p>
          {result.other_goals_affected.map((o) => (
            <p key={o.goal_id} className="mt-1 text-xs text-ink-3">{o.name}: fundable {inr(o.fundable_before)} → {inr(o.fundable_after)}/month</p>
          ))}
        </div>
      )}
    </div>
  )
}

function GoalCard({ plan, goal, annualReturn, onEdit, onDelete }) {
  const [open, setOpen] = useState(false)
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-semibold text-ink">{plan.name}</h2>
            <GoalStatusBadge status={plan.status} />
          </div>
          <p className="mt-0.5 text-xs text-ink-3">Priority {plan.priority}{plan.target_date ? ` · target ${monthLabel(plan.target_date)}` : ''}</p>
        </div>
        <div className="flex gap-1">
          <button type="button" aria-label={`Edit ${plan.name}`} className="rounded p-1.5 text-ink-3 hover:bg-slate-100" onClick={() => onEdit(goal)}><Pencil className="size-4" /></button>
          <button type="button" aria-label={`Delete ${plan.name}`} className="rounded p-1.5 text-ink-3 hover:bg-red-50 hover:text-red-700" onClick={() => onDelete(goal)}><Trash2 className="size-4" /></button>
        </div>
      </div>
      <div className="mt-4">
        <div className="mb-1 flex justify-between text-xs text-ink-2"><span>{inr(plan.current_amount)} saved</span><span>{plan.progress_pct.toFixed(0)}% of {inr(plan.target_amount)}</span></div>
        <Meter value={plan.progress_pct} label={`${plan.name} progress`} />
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div><dt className="text-xs text-ink-3">Needed / month</dt><dd className="font-semibold">{plan.required_monthly == null ? '—' : inr(plan.required_monthly)}</dd></div>
        <div><dt className="text-xs text-ink-3">You plan</dt><dd className="font-semibold">{inr(plan.planned_monthly)}</dd></div>
        <div><dt className="text-xs text-ink-3">Surplus can fund</dt><dd className="font-semibold">{inr(plan.fundable_monthly)}</dd></div>
        <div><dt className="text-xs text-ink-3">Reached (at that pace)</dt><dd className="font-semibold">{monthLabel(plan.completion_at_fundable) || 'not at this pace'}</dd></div>
      </dl>
      <p className="mt-3 text-sm text-ink-2">{plan.explanation}</p>
      {plan.options.length > 0 && (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-ink-2">{plan.options.map((o) => <li key={o.type}>{o.text}</li>)}</ul>
      )}
      <button type="button" className="mt-3 text-sm font-medium text-brand-700" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? 'Hide details' : 'What if I save more or less?'}
      </button>
      {open && (
        <>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 font-medium">Save per month</th><th className="pb-2 font-medium">Reached</th><th className="pb-2 font-medium">Meets target date</th><th className="pb-2 font-medium">Affordable</th></tr></thead>
              <tbody className="divide-y divide-line">
                {plan.sensitivity.map((r) => (
                  <tr key={r.change} className={r.change === 0 ? 'font-medium' : ''}>
                    <td className="tabular py-2">{inr(r.monthly)} {r.change === 0 && <span className="text-xs text-ink-3">(your plan)</span>}</td>
                    <td className="py-2">{monthLabel(r.completion) || 'never'}{r.months_to_complete != null && <span className="text-xs text-ink-3"> · {r.months_to_complete} months</span>}</td>
                    <td className="py-2">{r.meets_target_date == null ? '—' : r.meets_target_date ? 'Yes' : 'No'}</td>
                    <td className="py-2">{r.affordable ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <TryChanges plan={plan} annualReturn={annualReturn} />
        </>
      )}
    </Card>
  )
}

export default function Goals() {
  const [annualReturn, setAnnualReturn] = useState(0)
  const plans = useApi(`/goals/plan?annual_return=${annualReturn}`)
  const goals = useApi('/goals')
  const [editing, setEditing] = useState(null)

  const reload = () => { plans.reload(); goals.reload() }
  async function remove(goal) {
    if (!window.confirm(`Delete the goal "${goal.name}"?`)) return
    await api.del(`/goals/${goal.id}`)
    reload()
  }

  return (
    <>
      <PageHeader
        title="Goals"
        description="Goals are funded from your monthly surplus in priority order. See what each needs, what your surplus can actually cover, and when you'll get there."
        action={<Button onClick={() => setEditing({})}><Plus className="size-4" /> New goal</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm text-ink-2">
        <span>Assumed annual return on goal savings:</span>
        <Segmented label="Assumed annual return" options={RETURNS} value={annualReturn} onChange={setAnnualReturn} />
        {plans.meta && <span>Monthly surplus available: <strong className="text-ink">{inr(plans.meta.monthly_surplus)}</strong></span>}
      </div>
      {plans.loading && !plans.data ? <Loading /> : plans.error ? <ErrorState error={plans.error} onRetry={plans.reload} /> : plans.data.length === 0 ? (
        <EmptyState title="No goals yet">Add a goal with a target amount and date to get a savings plan.</EmptyState>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {plans.data.map((p) => (
            <GoalCard key={p.goal_id} plan={p} goal={goals.data?.find((g) => g.id === p.goal_id)} annualReturn={annualReturn} onEdit={setEditing} onDelete={remove} />
          ))}
        </div>
      )}
      <Modal title={editing?.id ? 'Edit goal' : 'New goal'} open={editing != null} onClose={() => setEditing(null)}>
        {editing && <GoalForm initial={editing.id ? editing : null} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload() }} />}
      </Modal>
      <Disclaimer>Goal plans are estimates based on your current surplus and the return you assume; actual returns and spending will vary.</Disclaimer>
    </>
  )
}
