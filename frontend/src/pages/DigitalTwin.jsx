import { ArrowRight, Database, Gauge, LineChart, Sparkles } from 'lucide-react'
import { Link } from 'react-router'
import { ProjectionChart, TrendChart } from '../charts/charts'
import {
  Card, Disclaimer, ErrorState, Loading, Meter, PageHeader, ScoreGauge, SourceBadge, StatusBadge,
} from '../components/ui'
import { useApi } from '../hooks/useApi'
import { assetLabel, dateLabel, inr, monthLabel, pct } from '../utils/format'

const SCENARIOS = [
  { title: 'Buy a ₹1,30,000 laptop', query: 'type=large_purchase&amount=130000' },
  { title: 'Income falls by 20%', query: 'type=income_change&pct=-20' },
  { title: 'Increase SIP by ₹5,000', query: 'type=sip_change&amount=5000' },
  { title: 'Save ₹15,000 more a month', query: 'type=extra_savings&amount=15000' },
]

function Step({ icon: Icon, n, title, children }) {
  return (
    <section className="relative">
      <div className="mb-3 flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-full bg-brand-600 text-xs font-semibold text-white">{n}</span>
        <Icon className="size-4 text-ink-3" aria-hidden />
        <h2 className="text-sm font-semibold tracking-wide text-ink uppercase">{title}</h2>
      </div>
      {children}
    </section>
  )
}

function Tile({ title, value, lines, source }) {
  return (
    <div className="rounded-xl border border-line bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2 text-xs font-medium text-ink-3">
        <span>{title}</span>
        <SourceBadge source={source} />
      </div>
      <div className="mt-1.5 text-xl font-semibold text-ink">{value}</div>
      <ul className="mt-2 space-y-0.5 text-xs text-ink-2">
        {lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
    </div>
  )
}

const STATUS_TONE = { strong: 'good', fair: 'warning', weak: 'serious', excluded: 'info' }

export default function DigitalTwin() {
  const twin = useApi('/digital-twin')
  const health = useApi('/health-score?compare_months=3')
  const projection = useApi('/forecast/cash-flow?horizon=6')
  const history = useApi('/digital-twin/history')
  const scores = useApi('/health-score/history')

  if (twin.loading || health.loading) return <Loading label="Rebuilding your Digital Twin…" />
  if (twin.error) return <ErrorState error={twin.error} onRetry={twin.reload} />
  if (health.error) return <ErrorState error={health.error} onRetry={health.reload} />
  const t = twin.data
  const h = health.data
  const allocation = Object.entries(t.investment_allocation).map(([k, v]) => `${assetLabel(k)} ${pct(v, 0)}`).join(' · ')

  return (
    <>
      <PageHeader
        title="Your Financial Digital Twin"
        description="A virtual model of your finances, rebuilt from your transactions, profile, investments, loans and goals every time something changes. It is what every analysis, forecast and simulation in FinTwin runs on."
      />
      <div className="space-y-8">
        <Step icon={Database} n={1} title="Current state">
          <p className="mb-3 text-sm text-ink-2">
            As of {dateLabel(t.as_of)} ·{' '}
            {t.window_months
              ? `monthly flows averaged over ${monthLabel(t.window_start)}–${monthLabel(t.window_end)} (${t.window_months} complete months)`
              : 'no complete month of transactions yet, so your declared profile values are used'}{' '}
            · {t.months_of_history} month(s) of history
          </p>
          {t.notes.map((n) => <p key={n} className="mb-2 text-sm text-amber-800">{n}</p>)}
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Tile title="Income" value={`${inr(t.monthly_income)}/mo`} source={t.sources.income} lines={[`Disposable after essentials & EMIs: ${inr(t.disposable_income)}`]} />
            <Tile title="Expenses" value={`${inr(t.monthly_expenses)}/mo`} source={t.sources.essential} lines={[`Essential ${inr(t.essential_expenses)}`, `Discretionary ${inr(t.discretionary_expenses)}`, `Burn rate ${inr(t.burn_rate_daily)}/day`]} />
            <Tile title="Savings" value={pct(t.savings_ratio)} lines={[`Monthly surplus ${inr(t.net_cash_flow)}`, `Cash balance ${inr(t.cash_balance)}`]} />
            <Tile title="Investments" value={inr(t.investments_value)} source={t.sources.investment_contributions} lines={[`Contributing ${inr(t.investment_contributions)}/mo (${pct(t.investment_rate)})`, allocation || 'No holdings recorded']} />
            <Tile title="Debt" value={inr(t.total_debt)} source={t.sources.debt_payments} lines={[`EMIs ${inr(t.debt_payments)}/mo`, `Debt-to-income ${pct(t.debt_to_income)}`]} />
            <Tile title="Emergency fund" value={inr(t.emergency_fund)} lines={[t.emergency_months == null ? 'Coverage n/a' : `Covers ${t.emergency_months.toFixed(1)} months (target 3–6)`]} />
            <Tile title="Goals" value={inr(t.goals_saved)} lines={[`${t.goals.length} goal(s) saved towards`, ...t.goals.slice(0, 2).map((g) => `${g.name}: ${g.progress_pct.toFixed(0)}%`)]} />
            <Tile title="Net worth" value={inr(t.net_worth)} lines={['Cash + emergency fund + investments + goal savings − loans']} />
          </div>
        </Step>

        <Step icon={Gauge} n={2} title="Financial health">
          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <div className="flex flex-col items-center">
                <ScoreGauge score={h.score} grade={h.grade} label={h.label} size={160} />
                {h.change && <p className="mt-4 text-sm text-ink-2">{h.change.summary}</p>}
                <Link to="/coach" className="mt-3 text-sm font-medium text-brand-700">Ask the coach why →</Link>
              </div>
            </Card>
            <Card title="How the score is calculated" subtitle="Each component maps one measured indicator to 0–100 using a published guideline; the score is the weighted average." className="lg:col-span-2">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-ink-3">
                    <tr><th className="pb-2 font-medium">Component</th><th className="pb-2 font-medium">Your value</th><th className="pb-2 font-medium">Target</th><th className="w-40 pb-2 font-medium">Score</th><th className="pb-2 text-right font-medium">Weight</th></tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {h.components.map((c) => (
                      <tr key={c.key} className="align-top" title={c.explanation || c.excluded_reason}>
                        <td className="py-2.5 pr-3">
                          <div className="font-medium text-ink">{c.label}</div>
                          <div className="mt-0.5 max-w-xs text-xs text-ink-3">{c.explanation || c.excluded_reason}</div>
                        </td>
                        <td className="py-2.5 pr-3 whitespace-nowrap text-ink-2">{c.value_display}</td>
                        <td className="py-2.5 pr-3 whitespace-nowrap text-ink-3">{c.target}</td>
                        <td className="py-2.5 pr-3">
                          {c.score == null ? <StatusBadge tone="info">not scored</StatusBadge> : (
                            <div className="flex items-center gap-2"><Meter value={c.score} label={c.label} /><span className="tabular w-8 text-right text-ink">{Math.round(c.score)}</span></div>
                          )}
                        </td>
                        <td className="tabular py-2.5 text-right text-ink-2">{(c.effective_weight * 100).toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
          {h.recommendations.length > 0 && (
            <Card title="What would raise it most" className="mt-4">
              <ul className="grid gap-3 md:grid-cols-2">
                {h.recommendations.slice(0, 4).map((r) => (
                  <li key={r.component} className="rounded-lg bg-slate-50 p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-ink">{r.title}</span>
                      <StatusBadge tone={STATUS_TONE[h.components.find((c) => c.key === r.component)?.status] ?? 'info'}>up to +{Math.round(r.potential_points)} pts</StatusBadge>
                    </div>
                    <p className="mt-1 text-ink-2">{r.action}</p>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </Step>

        <Step icon={LineChart} n={3} title="Predicted state">
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Projected cash balance" subtitle="Next 6 months, with the likely range">
              {projection.loading ? <Loading /> : projection.data?.status === 'ok' ? (
                <>
                  <ProjectionChart points={projection.data.forecast} />
                  <p className="mt-3 text-sm text-ink-2">{projection.data.explanation}</p>
                </>
              ) : <p className="text-sm text-ink-2">{projection.data?.message ?? 'Projection unavailable.'}</p>}
            </Card>
            <Card title="Net worth history" subtitle="Month-end snapshots of the twin">
              {history.data?.length ? (
                <TrendChart data={history.data} dataKey="net_worth" name="Net worth" xKey="as_of" />
              ) : <p className="text-sm text-ink-2">History appears after the first complete month.</p>}
            </Card>
            <Card title="Health score history" className="lg:col-span-2">
              {scores.data?.length ? (
                <TrendChart data={scores.data} dataKey="score" name="Health score" xKey="as_of" valueFormatter={(v) => v.toFixed(0)} yFormatter={(v) => v} domain={[0, 100]} height={200} />
              ) : <p className="text-sm text-ink-2">No score history yet.</p>}
            </Card>
          </div>
        </Step>

        <Step icon={Sparkles} n={4} title="Possible scenarios">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {SCENARIOS.map((s) => (
              <Link key={s.title} to={`/simulator?${s.query}`} className="group rounded-xl border border-line bg-white p-4 shadow-sm hover:border-brand-500">
                <div className="text-sm font-medium text-ink">{s.title}</div>
                <div className="mt-2 flex items-center gap-1 text-xs font-medium text-brand-700">Simulate <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" /></div>
              </Link>
            ))}
          </div>
        </Step>
      </div>
      <Disclaimer />
    </>
  )
}
