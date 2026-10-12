import { ArrowUpRight, Banknote, PiggyBank, ShieldCheck, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { FlowChart, ForecastChart } from '../charts/charts'
import {
  Button, Card, Disclaimer, EmptyState, ErrorState, GoalStatusBadge, Input, Kpi, Loading, Meter,
  PageHeader, RiskBadge, ScoreGauge, SeverityBadge,
} from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useApi } from '../hooks/useApi'
import { api, errorText } from '../services/api'
import { inr, pct } from '../utils/format'

function MoreLink({ to, children }) {
  return (
    <Link to={to} className="group inline-flex items-center gap-1 text-xs font-medium text-ink-2 transition duration-200 hover:text-ink">
      {children}
      <ArrowUpRight className="size-3.5 transition duration-200 ease-out-soft group-hover:translate-x-0.5 group-hover:-translate-y-0.5" strokeWidth={1.75} aria-hidden />
    </Link>
  )
}

const stagger = (i) => ({ '--i': i })

function QuickSimulation() {
  const [amount, setAmount] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function run(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { data } = await api.post('/simulation/what-if', { type: 'large_purchase', amount: Number(amount) })
      setResult(data)
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Quick what-if" subtitle="Can I afford a purchase today?" className="reveal lg:col-span-3" style={stagger(7)}>
      <form onSubmit={run} className="flex max-w-xl gap-2">
        <Input type="number" min="1" required placeholder="Amount in ₹, e.g. 130000" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Purchase amount" />
        <Button type="submit" loading={busy}>Simulate</Button>
      </form>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {result && (
        <div className="mt-4 max-w-3xl space-y-2 text-sm">
          <RiskBadge level={result.risk_level} />
          <p className="text-ink-2">{result.explanation}</p>
          <MoreLink to={`/simulator?type=large_purchase&amount=${amount}`}>Open in the simulator</MoreLink>
        </div>
      )}
    </Card>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const { data, error, loading, reload } = useApi('/dashboard')
  if (loading) return <Loading label="Building your Digital Twin…" />
  if (error) return <ErrorState error={error} onRetry={reload} />
  const { twin, health, trends, alerts, goals, forecast } = data
  const hasData = twin.window_months > 0 || twin.monthly_income > 0

  return (
    <>
      <div className="reveal" style={stagger(0)}>
        <PageHeader
          title={`Hello, ${user.full_name.split(' ')[0]}`}
          description={hasData ? (
            <>
              Your financial picture, based on {twin.window_months ? `your last ${twin.window_months} complete month(s)` : 'your declared profile'}.
              <span className="ml-2 font-mono text-xs text-ink-3">as of {twin.as_of}</span>
            </>
          ) : undefined}
        />
      </div>
      {!hasData && (
        <EmptyState title="Your Digital Twin needs data">
          <Link className="font-medium text-ink underline decoration-ink/20 underline-offset-4" to="/transactions">Import a bank statement</Link> or{' '}
          <Link className="font-medium text-ink underline decoration-ink/20 underline-offset-4" to="/profile">fill in your profile</Link> to get started.
        </EmptyState>
      )}

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card title="Financial health score" className="reveal lg:row-span-2" style={stagger(1)} action={<MoreLink to="/twin">Details</MoreLink>}>
          <div className="flex flex-col items-center gap-3 pt-2">
            <ScoreGauge score={health.score} grade={health.grade} label={health.label} size={160} />
          </div>
          <ul className="mt-8 space-y-3.5 border-t border-line pt-6">
            {health.components.filter((c) => c.score != null).map((c) => (
              <li key={c.key}>
                <div className="mb-1.5 flex justify-between text-xs"><span className="text-ink-2">{c.label}</span><span className="tabular font-medium text-ink">{Math.round(c.score)}</span></div>
                <Meter value={c.score} label={c.label} />
              </li>
            ))}
          </ul>
        </Card>

        <div className="reveal grid grid-cols-2 gap-4 lg:col-span-2 xl:grid-cols-3" style={stagger(2)}>
          <Kpi label="Cash balance" value={inr(twin.cash_balance)} icon={Wallet} />
          <Kpi label="Monthly income" value={inr(twin.monthly_income)} icon={TrendingUp} />
          <Kpi label="Monthly spending" value={inr(twin.monthly_expenses)} icon={TrendingDown} hint={`+ ${inr(twin.debt_payments)} EMIs`} />
          <Kpi label="Monthly surplus" value={inr(twin.net_cash_flow)} icon={Banknote} hint="after EMIs & SIPs" />
          <Kpi label="Savings ratio" value={pct(twin.savings_ratio)} icon={PiggyBank} hint="target ≥ 20%" />
          <Kpi label="Emergency fund" value={twin.emergency_months == null ? '—' : `${twin.emergency_months.toFixed(1)} months`} icon={ShieldCheck} hint="target 3–6" />
        </div>

        <Card title="Income vs spending" subtitle="Last 12 months" className="reveal lg:col-span-2" style={stagger(3)}>
          {trends.some((t) => t.income || t.expenses)
            ? <FlowChart data={trends} />
            : <p className="text-sm text-ink-2">No transactions in the last 12 months yet.</p>}
        </Card>

        <Card title="Risk alerts" className="reveal" style={stagger(4)} action={<MoreLink to="/risks">All alerts</MoreLink>}>
          {alerts.length === 0 ? <p className="text-sm text-ink-2">No active alerts.</p> : (
            <ul className="-my-3 divide-y divide-line">
              {alerts.slice(0, 4).map((a) => (
                <li key={a.id} className="py-3 text-sm">
                  <SeverityBadge level={a.severity} />
                  <p className="mt-1.5 text-ink">{a.title}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Goals" className="reveal" style={stagger(5)} action={<MoreLink to="/goals">Plan</MoreLink>}>
          {goals.length === 0 ? <p className="text-sm text-ink-2">No goals yet.</p> : (
            <ul className="-my-3 divide-y divide-line">
              {goals.slice(0, 4).map((g) => (
                <li key={g.goal_id} className="py-3 text-sm">
                  <div className="mb-2 flex items-center justify-between gap-2">
                    <span className="text-ink">{g.name}</span>
                    <GoalStatusBadge status={g.status} />
                  </div>
                  <Meter value={g.progress_pct} label={`${g.name} progress`} />
                  <p className="tabular mt-1.5 text-xs text-ink-3">{inr(g.current_amount)} of {inr(g.target_amount)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Spending forecast" subtitle={forecast.status === 'ok' ? `${forecast.model.label} · ${forecast.confidence} confidence` : undefined} className="reveal" style={stagger(6)} action={<MoreLink to="/forecasts">Forecasts</MoreLink>}>
          {forecast.status === 'ok' ? <ForecastChart history={forecast.history.slice(-6)} forecast={forecast.forecast} height={220} /> : <p className="text-sm text-ink-2">{forecast.message}</p>}
        </Card>

        <QuickSimulation />
      </div>
      <Disclaimer />
    </>
  )
}
