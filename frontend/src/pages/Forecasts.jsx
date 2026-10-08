import { useState } from 'react'
import { ForecastChart, ProjectionChart } from '../charts/charts'
import { Card, Disclaimer, ErrorState, Loading, PageHeader, Segmented, StatusBadge } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { inr, monthLabel, signed } from '../utils/format'

const CONFIDENCE_TONE = { high: 'good', medium: 'warning', low: 'serious' }

export default function Forecasts() {
  const [horizon, setHorizon] = useState(3)
  const expenses = useApi(`/forecast/expenses?horizon=${horizon}`)
  const cash = useApi(`/forecast/cash-flow?horizon=${horizon * 2}`)

  return (
    <>
      <PageHeader
        title="Forecasts"
        description="Statistical estimates of your coming months, made by the model that predicted your own recent spending best. Ranges show where the actual value is likely (80%) to fall."
        action={<Segmented label="Horizon" value={horizon} onChange={setHorizon} options={[{ value: 1, label: '1 month' }, { value: 3, label: '3 months' }, { value: 6, label: '6 months' }]} />}
      />
      {expenses.loading && !expenses.data ? <Loading label="Running the forecasting models…" /> : expenses.error ? <ErrorState error={expenses.error} onRetry={expenses.reload} /> : expenses.data.status !== 'ok' ? (
        <Card><p className="text-sm text-ink-2">{expenses.data.message}</p></Card>
      ) : (
        <div className="space-y-4">
          <Card
            title="Spending forecast"
            subtitle={`Model: ${expenses.data.model.label}`}
            action={<StatusBadge tone={CONFIDENCE_TONE[expenses.data.confidence]}>{expenses.data.confidence} confidence</StatusBadge>}
          >
            <ForecastChart history={expenses.data.history} forecast={expenses.data.forecast} />
            <p className="mt-3 text-sm text-ink-2">{expenses.data.explanation}</p>
            {expenses.data.notes.map((n) => <p key={n} className="mt-1 text-xs text-ink-3">{n}</p>)}
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title={`Next month by category (${monthLabel(expenses.data.forecast[0].month)})`}>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 font-medium">Category</th><th className="pb-2 text-right font-medium">Forecast</th><th className="pb-2 text-right font-medium">Recent avg</th><th className="pb-2 text-right font-medium">Change</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {expenses.data.categories.slice(0, 10).map((c) => (
                    <tr key={c.category}>
                      <td className="py-2 text-ink">{c.category}</td>
                      <td className="tabular py-2 text-right font-medium">{inr(c.forecast)}</td>
                      <td className="tabular py-2 text-right text-ink-2">{inr(c.recent_average)}</td>
                      <td className="tabular py-2 text-right text-ink-2">{c.change_pct == null ? '—' : signed(c.change_pct, (v) => `${v.toFixed(0)}%`)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <Card title="Which model, and why" subtitle={`Each model predicted your last ${expenses.data.model.backtest_origins} complete months; lower error is better.`}>
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 font-medium">Model</th><th className="pb-2 text-right font-medium">Avg. miss (MAE)</th><th className="pb-2 text-right font-medium">MAPE</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {expenses.data.model.backtest.map((b) => (
                    <tr key={b.model}>
                      <td className="py-2 text-ink">{b.label} {b.model === expenses.data.model.selected && <StatusBadge tone="good">selected</StatusBadge>}</td>
                      <td className="tabular py-2 text-right">{inr(b.mae)}</td>
                      <td className="tabular py-2 text-right text-ink-2">{b.mape == null ? '—' : `${(b.mape * 100).toFixed(1)}%`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {expenses.data.model.selection_rule && <p className="mt-3 text-xs text-ink-3">Rule: {expenses.data.model.selection_rule}.</p>}
            </Card>
          </div>

          <Card title="Cash-flow projection" subtitle={`Next ${horizon * 2} months`}>
            {cash.loading && !cash.data ? <Loading /> : cash.data?.status === 'ok' ? (
              <>
                <ProjectionChart points={cash.data.forecast} />
                <p className="mt-3 text-sm text-ink-2">{cash.data.explanation}</p>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="text-left text-xs text-ink-3"><tr><th className="pb-2 font-medium">Month</th><th className="pb-2 text-right font-medium">Income</th><th className="pb-2 text-right font-medium">Spending</th><th className="pb-2 text-right font-medium">EMIs</th><th className="pb-2 text-right font-medium">SIPs</th><th className="pb-2 text-right font-medium">Net</th></tr></thead>
                    <tbody className="divide-y divide-line">
                      {cash.data.forecast.map((p) => (
                        <tr key={p.month}>
                          <td className="py-2">{monthLabel(p.month)}</td>
                          <td className="tabular py-2 text-right">{inr(p.income)}</td>
                          <td className="tabular py-2 text-right">{inr(p.expenses)}</td>
                          <td className="tabular py-2 text-right">{inr(p.emi)}</td>
                          <td className="tabular py-2 text-right">{inr(p.investments)}</td>
                          <td className={`tabular py-2 text-right font-medium ${p.net_cash_flow < 0 ? 'text-red-700' : ''}`}>{inr(p.net_cash_flow)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {cash.data.notes.map((n) => <p key={n} className="mt-2 text-xs text-ink-3">{n}</p>)}
              </>
            ) : <p className="text-sm text-ink-2">{cash.data?.message}</p>}
          </Card>
        </div>
      )}
      <Disclaimer>Forecasts are statistical estimates based on your past spending, not guarantees.</Disclaimer>
    </>
  )
}
