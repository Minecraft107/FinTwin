import { ArrowRight, Bot, Gauge, LineChart, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { Meter, Reveal, RiskBadge, ScoreGauge, SeverityBadge } from '../components/ui'
import { useAuth } from '../context/AuthContext'

// Figures shown in the preview and the bento come from the seeded demo account.
const DEMO = {
  score: 65,
  grade: 'C',
  label: 'Fair',
  stats: [
    { label: 'Monthly surplus', value: '₹7,720' },
    { label: 'Savings ratio', value: '16.8%' },
    { label: 'Emergency fund', value: '1.5 months' },
  ],
  components: [
    { label: 'Debt burden', score: 89 },
    { label: 'Savings', score: 71 },
    { label: 'Emergency fund', score: 40 },
  ],
}

const STEPS = [
  { title: 'Bring your data', text: 'Import a bank statement or add transactions, loans, investments and goals.' },
  { title: 'Build the twin', text: 'Every entry is categorised and your financial state is rebuilt month by month.' },
  { title: 'Read your health', text: 'A 0–100 score from seven measured components, each one explained.' },
  { title: 'Test a decision', text: 'Simulate a purchase, a loan or a pay cut before it happens.' },
  { title: 'Ask why', text: 'The coach explains the result in plain language, using your own figures.' },
]

const STATS = [
  { value: '7', label: 'measured health components' },
  { value: '8', label: 'what-if change types' },
  { value: '13', label: 'guides behind the coach' },
]

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="grid size-8 place-items-center rounded-md bg-ink font-serif text-lg leading-none text-white">F</span>
      <span className="font-medium tracking-tight text-ink">FinTwin</span>
    </Link>
  )
}

function PrimaryCta({ user }) {
  const { demo } = useAuth()
  const navigate = useNavigate()
  const [busy, setBusy] = useState(false)

  async function openDemo() {
    if (user) return navigate('/dashboard')
    setBusy(true)
    try {
      await demo()
      navigate('/dashboard')
    } catch {
      navigate('/login') // demo login disabled or unreachable: the login page explains why
    } finally {
      setBusy(false)
    }
  }

  return (
    <button
      type="button"
      onClick={openDemo}
      disabled={busy}
      className="group inline-flex items-center gap-3 rounded-md bg-ink py-2 pr-2 pl-5 text-sm font-medium text-white transition duration-200 ease-out-soft hover:bg-[#3a3835] active:scale-[0.98] disabled:opacity-70"
    >
      {busy ? 'Opening the demo…' : user ? 'Open your dashboard' : 'Explore the demo'}
      <span className="grid size-7 place-items-center rounded bg-white/10 transition duration-300 ease-out-soft group-hover:translate-x-0.5">
        <ArrowRight className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
    </button>
  )
}

function TwinPreview() {
  return (
    <div className="rounded-2xl bg-ink/[0.03] p-2 ring-1 ring-line">
      <div className="overflow-hidden rounded-xl border border-line bg-white shadow-[0_30px_60px_-30px_rgba(31,30,28,0.25)]">
        <div className="flex items-center gap-1.5 border-b border-line px-4 py-3">
          <span className="size-2.5 rounded-full bg-slate-100 ring-1 ring-line" />
          <span className="size-2.5 rounded-full bg-slate-100 ring-1 ring-line" />
          <span className="size-2.5 rounded-full bg-slate-100 ring-1 ring-line" />
          <span className="ml-3 font-mono text-[11px] text-ink-3">fintwin · demo account</span>
        </div>
        <div className="grid gap-6 p-6 sm:grid-cols-[auto_1fr] sm:items-center">
          <ScoreGauge score={DEMO.score} grade={DEMO.grade} label={DEMO.label} size={128} />
          <dl className="divide-y divide-line">
            {DEMO.stats.map((s) => (
              <div key={s.label} className="flex items-baseline justify-between gap-4 py-2.5">
                <dt className="text-sm text-ink-2">{s.label}</dt>
                <dd className="tabular text-sm font-medium text-ink">{s.value}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="grid gap-px border-t border-line bg-line sm:grid-cols-2">
          <div className="bg-surface p-5">
            <p className="font-mono text-[11px] text-ink-3">What if · ₹1,30,000 laptop</p>
            <div className="mt-2 flex items-center gap-2">
              <RiskBadge level="LOW" />
              <span className="tabular text-xs text-ink-2">score 68 → 68 in a year</span>
            </div>
          </div>
          <div className="bg-surface p-5">
            <p className="font-mono text-[11px] text-ink-3">Risk alert</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <SeverityBadge level="HIGH" />
              <span className="text-xs text-ink-2">Food &amp; dining up 76%</span>
            </div>
          </div>
        </div>
      </div>
      <p className="px-2 pt-2.5 pb-0.5 font-mono text-[10.5px] text-ink-3">Figures from the seeded demo account.</p>
    </div>
  )
}

function Tile({ icon: Icon, title, text, className = '', index, children }) {
  return (
    <Reveal
      index={index}
      className={`flex flex-col rounded-xl border border-line bg-white p-7 transition-shadow duration-200 hover:shadow-lift ${className}`}
    >
      <span className="grid size-8 place-items-center rounded-md bg-brand-50 text-brand-700">
        <Icon className="size-4" strokeWidth={1.75} aria-hidden />
      </span>
      <h3 className="mt-5 text-lg font-medium tracking-tight text-ink">{title}</h3>
      <p className="mt-1.5 max-w-md text-sm text-ink-2">{text}</p>
      {children && <div className="mt-auto pt-6">{children}</div>}
    </Reveal>
  )
}

export default function Landing() {
  const { user } = useAuth()
  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-page">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[640px]"
        style={{ background: 'radial-gradient(60% 50% at 70% 0%, rgba(52,101,56,0.07), transparent 70%)' }}
      />

      <header className="relative mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Brand />
        <nav className="flex items-center gap-1" aria-label="Account">
          {user ? (
            <Link to="/dashboard" className="rounded-md bg-ink px-4 py-2 text-sm font-medium text-white transition duration-200 hover:bg-[#3a3835] active:scale-[0.98]">
              Open dashboard
            </Link>
          ) : (
            <>
              <Link to="/login" className="rounded-md px-4 py-2 text-sm text-ink-2 transition duration-200 hover:text-ink">Log in</Link>
              <Link to="/register" className="rounded-md border border-line bg-white px-4 py-2 text-sm font-medium text-ink transition duration-200 hover:border-ink/20 active:scale-[0.98]">
                Create an account
              </Link>
            </>
          )}
        </nav>
      </header>

      <main id="main">
        <section className="relative mx-auto grid max-w-6xl items-center gap-14 px-6 pt-12 pb-16 md:pt-20 lg:grid-cols-12 lg:pb-20">
          <div className="lg:col-span-6">
            <p className="reveal inline-flex items-center gap-2 font-mono text-xs text-ink-3" style={{ '--i': 0 }}>
              <span className="size-1.5 rounded-full bg-brand-600" aria-hidden />
              Financial health digital twin
            </p>
            <h1 className="reveal mt-5 font-serif text-[2.75rem] leading-[1.04] tracking-[-0.03em] text-ink sm:text-6xl lg:text-[4.1rem]" style={{ '--i': 1 }}>
              See where your money is heading, before you decide.
            </h1>
            <p className="reveal mt-6 max-w-[34rem] text-lg text-ink-2" style={{ '--i': 2 }}>
              FinTwin builds a model of your finances from your own transactions. It scores your financial health,
              forecasts your spending and shows what a purchase, a loan or a pay cut would change.
            </p>
            <div className="reveal mt-9 flex flex-wrap items-center gap-5" style={{ '--i': 3 }}>
              <PrimaryCta user={user} />
              {!user && (
                <Link to="/register" className="text-sm font-medium text-ink underline decoration-ink/20 underline-offset-4 transition hover:decoration-ink">
                  Start with your own data
                </Link>
              )}
            </div>
            <dl className="reveal mt-14 grid max-w-md grid-cols-3 divide-x divide-line border-y border-line" style={{ '--i': 4 }}>
              {STATS.map((s) => (
                <div key={s.label} className="px-4 py-4 first:pl-0">
                  <dt className="sr-only">{s.label}</dt>
                  <dd>
                    <span className="block font-serif text-3xl leading-none text-ink">{s.value}</span>
                    <span className="mt-2 block text-xs leading-snug text-ink-3">{s.label}</span>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="reveal lg:col-span-6" style={{ '--i': 2 }}>
            <TwinPreview />
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-16 lg:py-20" aria-labelledby="pillars-title">
          <div className="grid gap-12 lg:grid-cols-12">
            <Reveal className="lg:col-span-4">
              <p className="font-mono text-xs text-ink-3">What it does</p>
              <h2 id="pillars-title" className="mt-4 font-serif text-4xl leading-[1.1] tracking-[-0.02em] text-ink">
                One model of your money, four ways to use it.
              </h2>
              <p className="mt-4 max-w-sm text-sm text-ink-2">
                Every screen reads from the same Digital Twin, so the score, the forecast and the simulation always agree.
              </p>
            </Reveal>

            <div className="grid gap-4 sm:grid-cols-6 lg:col-span-8">
              <Tile
                index={0}
                className="sm:col-span-4"
                icon={Gauge}
                title="Analyze"
                text="A transparent 0–100 Financial Health Score built from savings, emergency cover, debt, cash-flow stability, investments, goals and spending."
              >
                <ul className="space-y-3">
                  {DEMO.components.map((c) => (
                    <li key={c.label}>
                      <div className="mb-1.5 flex justify-between text-xs">
                        <span className="text-ink-2">{c.label}</span>
                        <span className="tabular font-medium text-ink">{c.score}</span>
                      </div>
                      <Meter value={c.score} label={c.label} />
                    </li>
                  ))}
                </ul>
              </Tile>
              <Tile
                index={1}
                className="sm:col-span-2"
                icon={LineChart}
                title="Predict"
                text="Spending and cash-flow forecasts with an 80% likely range, from the model that best predicted your own history."
              />
              <Tile
                index={2}
                className="sm:col-span-2"
                icon={Sparkles}
                title="Simulate"
                text="Combine up to ten changes, from a big purchase to a new EMI, and compare 6 to 60 months side by side."
              />
              <Tile
                index={3}
                className="sm:col-span-4"
                icon={Bot}
                title="Decide"
                text="Ask questions in plain English, lakh and crore included. Affordability questions run the simulator before the coach answers."
              >
                <blockquote className="border-l-2 border-brand-600 pl-4 text-sm text-ink-2">
                  “Based on a simulation of spending ₹1,30,000 on a purchase now, this looks manageable. At your current
                  monthly surplus of ₹7,720, saving it would take about 17 months.”
                </blockquote>
              </Tile>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-16 lg:py-20" aria-labelledby="flow-title">
          <Reveal>
            <p className="font-mono text-xs text-ink-3">How it works</p>
            <h2 id="flow-title" className="mt-4 max-w-xl font-serif text-4xl leading-[1.1] tracking-[-0.02em] text-ink">
              From a bank statement to a decision.
            </h2>
          </Reveal>
          <ol className="mt-14 grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-5">
            {STEPS.map((step, i) => (
              <Reveal as="li" key={step.title} index={i} className="border-t border-ink/15 pt-5">
                <span className="font-mono text-xs text-ink-3">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="mt-3 font-medium tracking-tight text-ink">{step.title}</h3>
                <p className="mt-1.5 text-sm text-ink-2">{step.text}</p>
              </Reveal>
            ))}
          </ol>
        </section>

        <section className="mx-auto max-w-6xl px-6 pt-8 pb-28">
          <Reveal className="grid gap-10 rounded-2xl border border-line bg-surface p-10 md:p-16 lg:grid-cols-12 lg:items-end">
            <h2 className="font-serif text-4xl leading-[1.1] tracking-[-0.02em] text-ink lg:col-span-7 lg:text-5xl">
              The coach explains your numbers. It never makes them up.
            </h2>
            <div className="lg:col-span-5">
              <p className="text-sm text-ink-2">
                Every figure comes from FinTwin's own calculations. If a language model quotes a rupee amount or a
                percentage that is not in your data, its answer is discarded and a verified one is shown instead.
              </p>
              <div className="mt-7">
                <PrimaryCta user={user} />
              </div>
            </div>
          </Reveal>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-4 px-6 py-8 text-xs text-ink-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="max-w-xl">
            FinTwin is a decision-support and educational tool, not a licensed financial advisor. Forecasts and
            simulations are estimates based on your data and stated assumptions.
          </p>
          <nav className="flex gap-5" aria-label="Footer">
            <Link to="/login" className="transition hover:text-ink">Log in</Link>
            <Link to="/register" className="transition hover:text-ink">Create an account</Link>
          </nav>
        </div>
      </footer>
    </div>
  )
}
