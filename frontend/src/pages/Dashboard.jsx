import { Banknote, PiggyBank, ShieldCheck, TrendingDown, TrendingUp, Wallet } from 'lucide-react'
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
    <Card title="Quick what-if" subtitle="Can I afford a purchase today?">
      <form onSubmit={run} className="flex gap-2">
        <Input type="number" min="1" required placeholder="Amount in ₹, e.g. 130000" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Purchase amount" />
        <Button type="submit" loading={busy}>Simulate</Button>
      </form>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      {result && (
        <div className="mt-4 space-y-2 text-sm">
          <RiskBadge level={result.risk_level} />
          <p className="text-ink-2">{result.explanation}</p>
          <Link className="font-medium text-brand-700" to={`/simulator?type=large_purchase&amount=${amount}`}>
            Open in the simulator →
          </Link>
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
      <PageHeader
        title={`Hello, ${user.full_name.split(' ')[0]}`}
        description={hasData ? `Your financial picture as of ${twin.as_of}, based on ${twin.window_months ? `your last ${twin.window_months} complete month(s)` : 'your declared profile'}.` : undefined}
      />
      {!hasData && (
        <EmptyState title="Your Digital Twin needs data">
          <Link className="font-medium text-brand-700" to="/transactions">Import a bank statement</Link> or{' '}
          <Link className="font-medium text-brand-700" to="/profile">fill in your profile</Link> to get started.
        </EmptyState>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Financial Health Score" className="lg:row-span-2" action={<Link to="/twin" className="text-xs font-medium text-brand-700">Details →</Link>}>
          <div className="flex flex-col items-center gap-3">
            <ScoreGauge score={health.score} grade={health.grade} label={health.label} size={160} />
          </div>
          <ul className="mt-5 space-y-3">
            {health.components.filter((c) => c.score != null).map((c) => (
              <li key={c.key}>
                <div className="mb-1 flex justify-between text-xs"><span className="text-ink-2">{c.label}</span><span className="tabular font-medium text-ink">{Math.round(c.score)}</span></div>
                <Meter value={c.score} label={c.label} />
              </li>
            ))}
          </ul>
        </Card>

        <div className="grid grid-cols-2 gap-4 lg:col-span-2 xl:grid-cols-3">
          <Kpi label="Cash balance" value={inr(twin.cash_balance)} icon={Wallet} />
          <Kpi label="Monthly income" value={inr(twin.monthly_income)} icon={TrendingUp} />
          <Kpi label="Monthly spending" value={inr(twin.monthly_expenses)} icon={TrendingDown} hint={`+ ${inr(twin.debt_payments)} EMIs`} />
          <Kpi label="Monthly surplus" value={inr(twin.net_cash_flow)} icon={Banknote} hint="after EMIs & SIPs" />
          <Kpi label="Savings ratio" value={pct(twin.savings_ratio)} icon={PiggyBank} hint="target ≥ 20%" />
          <Kpi label="Emergency fund" value={twin.emergency_months == null ? '—' : `${twin.emergency_months.toFixed(1)} months`} icon={ShieldCheck} hint="target 3–6" />
        </div>

        <Card title="Income vs spending" subtitle="Last 12 months" className="lg:col-span-2">
          {trends.some((t) => t.income || t.expenses)
            ? <FlowChart data={trends} />
            : <p className="text-sm text-ink-2">No transactions in the last 12 months yet.</p>}
        </Card>

        <Card title="Risk alerts" action={<Link to="/risks" className="text-xs font-medium text-brand-700">All alerts →</Link>}>
          {alerts.length === 0 ? <p className="text-sm text-ink-2">No active alerts.</p> : (
            <ul className="space-y-3">
              {alerts.slice(0, 4).map((a) => (
                <li key={a.id} className="text-sm">
                  <SeverityBadge level={a.severity} />
                  <p className="mt-1 font-medium text-ink">{a.title}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Goals" action={<Link to="/goals" className="text-xs font-medium text-brand-700">Plan →</Link>}>
          {goals.length === 0 ? <p className="text-sm text-ink-2">No goals yet.</p> : (
            <ul className="space-y-4">
              {goals.slice(0, 4).map((g) => (
                <li key={g.goal_id} className="text-sm">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-medium text-ink">{g.name}</span>
                    <GoalStatusBadge status={g.status} />
                  </div>
                  <Meter value={g.progress_pct} label={`${g.name} progress`} />
                  <p className="mt-1 text-xs text-ink-3">{inr(g.current_amount)} of {inr(g.target_amount)}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Spending forecast" subtitle={forecast.status === 'ok' ? `${forecast.model.label} · ${forecast.confidence} confidence` : undefined} action={<Link to="/forecasts" className="text-xs font-medium text-brand-700">Forecasts →</Link>}>
          {forecast.status === 'ok' ? <ForecastChart history={forecast.history.slice(-6)} forecast={forecast.forecast} height={220} /> : <p className="text-sm text-ink-2">{forecast.message}</p>}
        </Card>

        <QuickSimulation />
      </div>
      <Disclaimer />
    </>
  )
}
