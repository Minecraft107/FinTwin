import { useState } from 'react'
import { CategoryBars, FlowChart, TrendChart } from '../charts/charts'
import { Card, EmptyState, ErrorState, Input, Kpi, Loading, PageHeader, Segmented } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { dateLabel, inr, pct, signed } from '../utils/format'

const RANGES = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '3m', label: '3 months' },
  { value: '6m', label: '6 months' },
  { value: '12m', label: '12 months' },
  { value: 'custom', label: 'Custom' },
]

function Change({ change, upIsGood }) {
  if (!change || change.pct == null) return null
  const good = upIsGood ? change.abs >= 0 : change.abs <= 0
  // A percentage of a near-zero base (e.g. +1768%) says nothing; show rupees instead.
  const text = Math.abs(change.pct) > 300 ? signed(change.abs) : signed(change.pct, (v) => `${v.toFixed(0)}%`)
  return <span className={good ? 'text-green-700' : 'text-red-700'}>{text} vs previous period</span>
}

export default function Analytics() {
  const [range, setRange] = useState('3m')
  const [custom, setCustom] = useState({ from: '', to: '' })
  const query = range === 'custom' ? (custom.from && custom.to ? `from=${custom.from}&to=${custom.to}` : null) : `range=${range}`
  const overview = useApi(query && `/analytics/overview?${query}`)
  const categories = useApi(query && `/analytics/categories?${query}`)
  const trends = useApi(query && `/analytics/trends?${query}`)
  const merchants = useApi(query && `/analytics/merchants?${query}&limit=8`)

  const o = overview.data
  const granularity = trends.meta?.granularity
  const xFormatter = granularity === 'day' ? (d) => dateLabel(d).replace(/ \d{4}$/, '') : undefined

  return (
    <>
      <PageHeader title="Spending analytics" description="Where your money comes from and where it goes, for any period." />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Segmented label="Date range" options={RANGES} value={range} onChange={setRange} />
        {range === 'custom' && (
          <div className="flex items-center gap-2">
            <Input type="date" aria-label="From" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
            <span className="text-ink-3">to</span>
            <Input type="date" aria-label="To" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
          </div>
        )}
        {overview.meta?.from && <span className="text-sm text-ink-3">{dateLabel(overview.meta.from)} – {dateLabel(overview.meta.to)}</span>}
      </div>

      {!query ? <EmptyState title="Pick a start and end date" /> : overview.loading && !o ? <Loading /> : overview.error ? <ErrorState error={overview.error} onRetry={overview.reload} /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Income" value={inr(o.current.income)} delta={<Change change={o.change.income} upIsGood />} />
            <Kpi label="Spending" value={inr(o.current.expenses)} delta={<Change change={o.change.expenses} />} hint={`${inr(o.current.avg_daily_spend)}/day`} />
            <Kpi label="Net cash flow" value={inr(o.current.net_cash_flow)} delta={<Change change={o.change.net_cash_flow} upIsGood />} hint="after EMIs & investments" />
            <Kpi label="Savings ratio" value={pct(o.current.savings_ratio)} hint={`${o.current.transaction_count} transactions`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Essential vs discretionary" subtitle="Share of spending (EMIs and investments shown separately)">
              {o.current.expenses ? (
                <>
                  <div className="flex h-3 w-full overflow-hidden rounded-full" role="img" aria-label={`Essential ${pct(o.essential_share, 0)}, discretionary ${pct(o.discretionary_share, 0)}`}>
                    <div className="bg-series-1" style={{ width: `${o.essential_share * 100}%` }} />
                    <div className="w-0.5 bg-white" />
                    <div className="flex-1 bg-series-2" />
                  </div>
                  <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
                    <div><dt className="flex items-center gap-2 text-ink-3"><span className="size-2 rounded-full bg-series-1" />Essential</dt><dd className="mt-1 text-lg font-semibold">{inr(o.current.essential)} <span className="text-sm font-normal text-ink-3">{pct(o.essential_share, 0)}</span></dd></div>
                    <div><dt className="flex items-center gap-2 text-ink-3"><span className="size-2 rounded-full bg-series-2" />Discretionary</dt><dd className="mt-1 text-lg font-semibold">{inr(o.current.discretionary)} <span className="text-sm font-normal text-ink-3">{pct(o.discretionary_share, 0)}</span></dd></div>
                    <div><dt className="text-ink-3">EMIs</dt><dd className="mt-1 font-medium">{inr(o.current.debt_payments)}</dd></div>
                    <div><dt className="text-ink-3">Investments</dt><dd className="mt-1 font-medium">{inr(o.current.investments)}</dd></div>
                  </dl>
                </>
              ) : <p className="text-sm text-ink-2">No spending in this period.</p>}
            </Card>
            <Card title="Spending by category" subtitle="Includes EMIs and investments">
              {categories.data?.length ? <CategoryBars data={categories.data.slice(0, 10)} /> : <p className="text-sm text-ink-2">No spending in this period.</p>}
            </Card>
          </div>

          <Card title="Income vs spending" subtitle={granularity === 'day' ? 'Per day' : 'Per month'}>
            {trends.data?.some((t) => t.income || t.expenses)
              ? <FlowChart data={trends.data} xFormatter={xFormatter} />
              : <p className="text-sm text-ink-2">No transactions in this period.</p>}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Cash balance" subtitle="Running balance — your savings trend">
              {trends.data && <TrendChart data={trends.data} dataKey="cash_balance" name="Cash balance" xFormatter={xFormatter} />}
            </Card>
            <Card title="Category changes" subtitle="Compared with the previous period of the same length">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 font-medium">Category</th><th className="pb-2 text-right font-medium">This period</th><th className="pb-2 text-right font-medium">Change</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {(categories.data ?? []).slice(0, 8).map((c) => (
                    <tr key={c.category}>
                      <td className="py-2 text-ink">{c.category} <span className="text-xs text-ink-3">{c.kind}</span></td>
                      <td className="tabular py-2 text-right">{inr(c.total)}</td>
                      <td className={`tabular py-2 text-right ${c.change_pct == null ? 'text-ink-3' : c.change_pct > 0 ? 'text-red-700' : 'text-green-700'}`}>{c.change_pct == null ? 'new' : signed(c.change_pct, (v) => `${v.toFixed(0)}%`)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <Card title="Top merchants">
            <ul className="divide-y divide-line text-sm">
              {(merchants.data ?? []).map((m) => (
                <li key={m.merchant} className="flex justify-between gap-3 py-2">
                  <span className="truncate text-ink">{m.merchant} <span className="text-xs text-ink-3">· {m.category} · {m.count}×</span></span>
                  <span className="tabular font-medium">{inr(m.total)}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </>
  )
}
