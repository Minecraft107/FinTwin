import { Bot, Gauge, LineChart, Sparkles } from 'lucide-react'
import { Link } from 'react-router'
import { useAuth } from '../context/AuthContext'

const PILLARS = [
  { icon: Gauge, title: 'Analyze', text: 'A live Digital Twin of your finances and a transparent 0–100 Financial Health Score, with every component explained.' },
  { icon: LineChart, title: 'Predict', text: 'Machine-learning forecasts of spending and cash flow, with honest uncertainty ranges and anomaly alerts.' },
  { icon: Sparkles, title: 'Simulate', text: 'What-if scenarios — a laptop, a loan, a pay cut — computed month by month before you decide.' },
  { icon: Bot, title: 'Decide', text: 'An AI coach that explains your own numbers and never invents them.' },
]

const FLOW = ['Your data', 'Digital Twin', 'Analyze · Predict · Simulate', 'Your decision', 'AI Coach']

export default function Landing() {
  const { user } = useAuth()
  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-page">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <div className="grid size-8 place-items-center rounded-lg bg-brand-600 text-sm font-bold text-white">F</div>
          <span className="font-semibold">FinTwin</span>
        </div>
        <nav className="flex gap-2">
          {user ? (
            <Link to="/dashboard" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">Open dashboard</Link>
          ) : (
            <>
              <Link to="/login" className="rounded-lg px-4 py-2 text-sm font-medium text-ink-2 hover:bg-slate-100">Log in</Link>
              <Link to="/register" className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700">Get started</Link>
            </>
          )}
        </nav>
      </header>

      <section className="mx-auto max-w-6xl px-6 pt-12 pb-16 text-center">
        <p className="text-sm font-semibold tracking-wide text-brand-700 uppercase">AI-Powered Financial Health Digital Twin</p>
        <h1 className="mx-auto mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-ink sm:text-5xl">
          Analyze. Predict. Simulate. Decide better.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-ink-2">
          FinTwin builds a virtual model of your financial life from your transactions, then shows where you stand,
          where you're heading, and what each decision would change.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <Link to={user ? '/dashboard' : '/login'} className="rounded-lg bg-brand-600 px-5 py-2.5 font-medium text-white hover:bg-brand-700">
            {user ? 'Go to your dashboard' : 'Try the demo'}
          </Link>
          <Link to="/register" className="rounded-lg border border-line bg-white px-5 py-2.5 font-medium text-ink hover:bg-slate-50">
            Create an account
          </Link>
        </div>
        <ol className="mx-auto mt-12 flex max-w-4xl flex-wrap items-center justify-center gap-2 text-sm text-ink-2" aria-label="How FinTwin works">
          {FLOW.map((step, i) => (
            <li key={step} className="flex items-center gap-2">
              <span className="rounded-full border border-line bg-white px-3 py-1">{step}</span>
              {i < FLOW.length - 1 && <span aria-hidden className="text-ink-3">→</span>}
            </li>
          ))}
        </ol>
      </section>

      <section className="mx-auto grid max-w-6xl gap-4 px-6 pb-20 sm:grid-cols-2 lg:grid-cols-4">
        {PILLARS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-xl border border-line bg-white p-5 shadow-sm">
            <Icon className="size-6 text-brand-600" aria-hidden />
            <h2 className="mt-3 font-semibold text-ink">{title}</h2>
            <p className="mt-1 text-sm text-ink-2">{text}</p>
          </div>
        ))}
      </section>

      <footer className="border-t border-line py-6 text-center text-xs text-ink-3">
        FinTwin is a decision-support and educational tool, not a licensed financial advisor.
      </footer>
    </div>
  )
}
