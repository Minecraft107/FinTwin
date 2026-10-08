import { Pencil, Plus, Trash2, Upload } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  Button, Card, EmptyState, ErrorState, Field, Input, Loading, Modal, PageHeader, Select, StatusBadge,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api, errorText, request } from '../services/api'
import { dateLabel, inr, today } from '../utils/format'

const PER_PAGE = 25
const METHODS = ['upi', 'card', 'cash', 'netbanking', 'auto_debit', 'other']
const SOURCE_LABEL = { rule: 'auto (rules)', ml: 'auto (ML)', memory: 'learned', manual: 'set by you', import: 'imported' }

function TransactionForm({ categories, initial, onSaved, onCancel }) {
  const [form, setForm] = useState(
    initial ?? { date: today(), amount: '', type: 'expense', description: '', merchant: '', category_id: '', payment_method: 'upi', is_recurring: false },
  )
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value })
  const options = categories.filter((c) => (form.type === 'income') === (c.kind === 'income'))

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    const body = {
      ...form,
      amount: Number(form.amount),
      merchant: form.merchant || null,
      category_id: form.category_id ? Number(form.category_id) : null,
    }
    try {
      if (initial?.id) {
        const { id, ...rest } = body
        await api.put(`/transactions/${id}`, rest.category_id == null ? { ...rest, category_id: undefined } : rest)
      } else {
        await api.post('/transactions', body)
      }
      onSaved()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
      <Field label="Type">
        <Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value, category_id: '' })}>
          <option value="expense">Expense</option>
          <option value="income">Income</option>
        </Select>
      </Field>
      <Field label="Date"><Input type="date" required max={today()} value={form.date} onChange={set('date')} /></Field>
      <Field label="Amount (₹)"><Input type="number" required min="0.01" step="0.01" value={form.amount} onChange={set('amount')} /></Field>
      <Field label="Category" hint={initial?.id ? 'Changing it teaches FinTwin for next time.' : 'Leave on Auto to categorise automatically.'}>
        <Select value={form.category_id} onChange={set('category_id')}>
          <option value="">{initial?.id ? 'Keep current' : 'Auto-categorise'}</option>
          {options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </Field>
      <div className="sm:col-span-2"><Field label="Description"><Input required maxLength={255} value={form.description} onChange={set('description')} placeholder="e.g. UPI/1234/SWIGGY ORDER" /></Field></div>
      <Field label="Merchant (optional)"><Input maxLength={120} value={form.merchant ?? ''} onChange={set('merchant')} /></Field>
      <Field label="Payment method">
        <Select value={form.payment_method} onChange={set('payment_method')}>
          {METHODS.map((m) => <option key={m} value={m}>{m.replace('_', ' ')}</option>)}
        </Select>
      </Field>
      <label className="flex items-center gap-2 text-sm text-ink-2 sm:col-span-2">
        <input type="checkbox" checked={form.is_recurring} onChange={set('is_recurring')} /> Recurring (e.g. rent, subscription, EMI)
      </label>
      {error && <p className="text-sm text-red-700 sm:col-span-2" role="alert">{error}</p>}
      <div className="flex justify-end gap-2 sm:col-span-2">
        <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" loading={busy}>{initial?.id ? 'Save changes' : 'Add transaction'}</Button>
      </div>
    </form>
  )
}

const ROW_TONE = { ok: 'good', warning: 'warning', duplicate: 'info', error: 'critical' }

function ImportWizard({ categories, onDone }) {
  const [preview, setPreview] = useState(null)
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [imported, setImported] = useState(null)

  async function upload(file) {
    setBusy(true)
    setError('')
    const body = new FormData()
    body.append('file', file)
    try {
      const { data } = await request('/transactions/import/preview', { method: 'POST', body })
      setPreview(data)
      setRows(data.rows.map((r) => ({ ...r, include: r.status === 'ok' || r.status === 'warning' })))
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function commit() {
    setBusy(true)
    setError('')
    try {
      const transactions = rows.filter((r) => r.include && r.transaction).map((r) => r.transaction)
      const { data } = await api.post('/transactions/import', { transactions })
      setImported(data.imported)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const update = (i, patch) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))
  const selected = rows.filter((r) => r.include).length

  if (imported != null) {
    return (
      <div className="text-sm">
        <StatusBadge tone="good">Imported {imported} transaction(s)</StatusBadge>
        <p className="mt-3 text-ink-2">Your Digital Twin, health score and alerts have been recalculated.</p>
        <div className="mt-4 flex justify-end"><Button onClick={onDone}>Done</Button></div>
      </div>
    )
  }
  if (!preview) {
    return (
      <div className="text-sm text-ink-2">
        <p>Upload a CSV bank statement. Columns are matched by name: <code>date, description, amount, type, category</code>, or bank style <code>Txn Date, Narration, Withdrawal Amt, Deposit Amt</code>. Nothing is saved until you confirm.</p>
        <label className="mt-4 flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-line p-8 text-center hover:border-brand-500">
          <Upload className="size-6 text-ink-3" aria-hidden />
          <span className="font-medium text-ink">{busy ? 'Checking your file…' : 'Choose a .csv file'}</span>
          <input type="file" accept=".csv,text/csv" className="sr-only" disabled={busy} onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
        </label>
        {error && <p className="mt-3 text-red-700" role="alert">{error}</p>}
      </div>
    )
  }
  const s = preview.summary
  return (
    <div className="text-sm">
      <div className="mb-3 flex flex-wrap gap-2">
        <StatusBadge tone="good">{s.ok} ready</StatusBadge>
        <StatusBadge tone="warning">{s.warning} with warnings</StatusBadge>
        <StatusBadge tone="info">{s.duplicate} possible duplicates</StatusBadge>
        <StatusBadge tone="critical">{s.error} errors</StatusBadge>
      </div>
      <div className="max-h-[55vh] overflow-auto rounded-lg border border-line">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-50 text-left text-ink-3">
            <tr><th className="p-2">Import</th><th className="p-2">Row</th><th className="p-2">Status</th><th className="p-2">Date</th><th className="p-2">Description</th><th className="p-2 text-right">Amount</th><th className="p-2">Category</th><th className="p-2">Notes</th></tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.map((r, i) => (
              <tr key={r.row} className={r.status === 'error' ? 'bg-red-50/50' : ''}>
                <td className="p-2"><input type="checkbox" aria-label={`Import row ${r.row}`} disabled={!r.transaction} checked={r.include} onChange={(e) => update(i, { include: e.target.checked })} /></td>
                <td className="p-2 text-ink-3">{r.row}</td>
                <td className="p-2"><StatusBadge tone={ROW_TONE[r.status]}>{r.duplicate_of ? `duplicate (${r.duplicate_of})` : r.status}</StatusBadge></td>
                <td className="p-2 whitespace-nowrap">{r.transaction?.date ?? '—'}</td>
                <td className="max-w-56 truncate p-2" title={r.transaction?.description}>{r.transaction?.description ?? '—'}</td>
                <td className="tabular p-2 text-right whitespace-nowrap">{r.transaction ? `${r.transaction.type === 'income' ? '+' : '−'}${inr(r.transaction.amount)}` : '—'}</td>
                <td className="p-2">
                  {r.transaction && (
                    <Select aria-label={`Category for row ${r.row}`} className="!py-1 text-xs" value={r.transaction.category_id}
                      onChange={(e) => update(i, { transaction: { ...r.transaction, category_id: Number(e.target.value), category_source: 'manual', category_confidence: null } })}>
                      {categories.filter((c) => (r.transaction.type === 'income') === (c.kind === 'income')).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </Select>
                  )}
                </td>
                <td className="max-w-64 p-2 text-ink-2">{[...r.errors, ...r.warnings].join(' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="mt-3 text-red-700" role="alert">{error}</p>}
      <div className="mt-4 flex justify-between gap-2">
        <Button variant="secondary" onClick={() => setPreview(null)}>Choose another file</Button>
        <Button onClick={commit} loading={busy} disabled={!selected}>Import {selected} row(s)</Button>
      </div>
    </div>
  )
}

export default function Transactions() {
  const [filters, setFilters] = useState({ q: '', type: '', category_id: '', from: '', to: '' })
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState(null)
  const [importing, setImporting] = useState(false)
  const categories = useApi('/categories')
  const query = useMemo(() => {
    const params = new URLSearchParams({ page, per_page: PER_PAGE })
    Object.entries(filters).forEach(([k, v]) => v && params.set(k, v))
    return `/transactions?${params}`
  }, [filters, page])
  const list = useApi(query)
  const setFilter = (k) => (e) => {
    setPage(1)
    setFilters({ ...filters, [k]: e.target.value })
  }

  async function remove(t) {
    if (!window.confirm(`Delete "${t.description}" (${inr(t.amount)})?`)) return
    await api.del(`/transactions/${t.id}`)
    list.reload()
  }

  const pages = list.meta ? Math.max(1, Math.ceil(list.meta.total / PER_PAGE)) : 1
  return (
    <>
      <PageHeader
        title="Transactions"
        description="Every transaction feeds your Digital Twin. Categories are assigned automatically; correct one and FinTwin remembers it."
        action={
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setImporting(true)}><Upload className="size-4" /> Import CSV</Button>
            <Button onClick={() => setEditing({})}><Plus className="size-4" /> Add</Button>
          </div>
        }
      />
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Input placeholder="Search description or merchant" aria-label="Search" value={filters.q} onChange={setFilter('q')} />
          <Select aria-label="Type" value={filters.type} onChange={setFilter('type')}>
            <option value="">All types</option><option value="expense">Expenses</option><option value="income">Income</option>
          </Select>
          <Select aria-label="Category" value={filters.category_id} onChange={setFilter('category_id')}>
            <option value="">All categories</option>
            {(categories.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Input type="date" aria-label="From date" value={filters.from} onChange={setFilter('from')} />
          <Input type="date" aria-label="To date" value={filters.to} onChange={setFilter('to')} />
        </div>
        {list.loading && !list.data ? <Loading /> : list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : list.data.length === 0 ? (
          <EmptyState title="No transactions found">Add one, import a CSV, or clear the filters.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-3">
                <tr><th className="pb-2 font-medium">Date</th><th className="pb-2 font-medium">Description</th><th className="pb-2 font-medium">Category</th><th className="pb-2 text-right font-medium">Amount</th><th className="pb-2" /></tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.data.map((t) => (
                  <tr key={t.id}>
                    <td className="py-2.5 pr-3 whitespace-nowrap text-ink-2">{dateLabel(t.date)}</td>
                    <td className="max-w-xs py-2.5 pr-3"><div className="truncate text-ink" title={t.description}>{t.description}</div>{t.merchant && <div className="text-xs text-ink-3">{t.merchant}</div>}</td>
                    <td className="py-2.5 pr-3 whitespace-nowrap">
                      <span className="inline-flex items-center gap-1.5 text-ink-2"><span className="size-2 rounded-full" style={{ background: t.category.color }} />{t.category.name}</span>
                      <div className="text-[11px] text-ink-3">{SOURCE_LABEL[t.category_source]}{t.category_confidence != null && t.category_source === 'ml' ? ` · ${Math.round(t.category_confidence * 100)}%` : ''}</div>
                    </td>
                    <td className={`tabular py-2.5 pr-3 text-right whitespace-nowrap font-medium ${t.type === 'income' ? 'text-green-700' : 'text-ink'}`}>{t.type === 'income' ? '+' : '−'}{inr(t.amount)}</td>
                    <td className="py-2.5 text-right whitespace-nowrap">
                      <button type="button" className="rounded p-1.5 text-ink-3 hover:bg-slate-100" aria-label={`Edit ${t.description}`} onClick={() => setEditing({ ...t, category_id: '' })}><Pencil className="size-4" /></button>
                      <button type="button" className="rounded p-1.5 text-ink-3 hover:bg-red-50 hover:text-red-700" aria-label={`Delete ${t.description}`} onClick={() => remove(t)}><Trash2 className="size-4" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {list.meta && (
          <div className="mt-4 flex items-center justify-between text-sm text-ink-2">
            <span>{list.meta.total} transaction(s)</span>
            <div className="flex items-center gap-2">
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span>Page {page} of {pages}</span>
              <Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        )}
      </Card>

      <Modal title={editing?.id ? 'Edit transaction' : 'Add transaction'} open={editing != null} onClose={() => setEditing(null)}>
        {editing && categories.data && (
          <TransactionForm
            categories={categories.data}
            initial={editing.id ? { id: editing.id, date: editing.date, amount: editing.amount, type: editing.type, description: editing.description, merchant: editing.merchant ?? '', category_id: '', payment_method: editing.payment_method, is_recurring: editing.is_recurring } : null}
            onCancel={() => setEditing(null)}
            onSaved={() => { setEditing(null); list.reload() }}
          />
        )}
      </Modal>
      <Modal title="Import transactions from CSV" open={importing} onClose={() => setImporting(false)} wide>
        {importing && categories.data && <ImportWizard categories={categories.data} onDone={() => { setImporting(false); list.reload() }} />}
      </Modal>
    </>
  )
}
