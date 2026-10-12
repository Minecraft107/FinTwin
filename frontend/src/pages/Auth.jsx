import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router'
import { Button, Field, Input } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { errorText } from '../services/api'

function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="relative grid min-h-[100dvh] place-items-center px-4 py-16">
      <Link
        to="/"
        className="group absolute top-5 left-4 inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-ink-2 transition duration-200 hover:bg-white hover:text-ink sm:top-6 sm:left-6"
      >
        <ArrowLeft className="size-4 transition duration-200 group-hover:-translate-x-0.5" strokeWidth={1.75} aria-hidden />
        Back to home
      </Link>
      <div className="w-full max-w-sm">
        <Link to="/" className="mb-6 flex items-center justify-center gap-2">
          <div className="grid size-9 place-items-center rounded-md bg-ink font-serif text-xl leading-none text-white">F</div>
          <span className="text-lg font-medium tracking-tight">FinTwin</span>
        </Link>
        <div className="rounded-xl border border-line bg-white p-7">
          <h1 className="font-serif text-[1.75rem] leading-tight tracking-[-0.02em] text-ink">{title}</h1>
          <p className="mt-1 text-sm text-ink-2">{subtitle}</p>
          <div className="mt-5">{children}</div>
        </div>
        <p className="mt-4 text-center text-sm text-ink-2">{footer}</p>
      </div>
    </div>
  )
}

function useAfterLogin() {
  const navigate = useNavigate()
  const location = useLocation()
  return () => navigate(location.state?.from ?? '/dashboard', { replace: true })
}

export function Login() {
  const { login, demo } = useAuth()
  const done = useAfterLogin()
  const [form, setForm] = useState({ email: '', password: '' })
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState('')

  async function run(kind, fn) {
    setBusy(kind)
    setError('')
    try {
      await fn()
      done()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Log in to see your Financial Digital Twin."
      footer={<>New here? <Link to="/register" className="font-medium text-brand-700">Create an account</Link></>}
    >
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run('login', () => login(form.email, form.password)) }}>
        <Field label="Email">
          <Input type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Password">
          <Input type="password" autoComplete="current-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
        <Button type="submit" className="w-full" loading={busy === 'login'}>Log in</Button>
      </form>
      <div className="my-4 flex items-center gap-3 text-xs text-ink-3">
        <span className="h-px flex-1 bg-line" /> or <span className="h-px flex-1 bg-line" />
      </div>
      <Button variant="secondary" className="w-full" loading={busy === 'demo'} onClick={() => run('demo', demo)}>
        Explore the demo account
      </Button>
      <p className="mt-2 text-center text-xs text-ink-3">24 months of realistic sample data — no sign-up needed.</p>
    </AuthLayout>
  )
}

export function Register() {
  const { register } = useAuth()
  const done = useAfterLogin()
  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await register(form)
      done()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Start with your profile or import a bank statement."
      footer={<>Already have an account? <Link to="/login" className="font-medium text-brand-700">Log in</Link></>}
    >
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Full name">
          <Input required autoComplete="name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </Field>
        <Field label="Email">
          <Input type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Password" hint="At least 8 characters, with a letter and a digit.">
          <Input type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
        <Button type="submit" className="w-full" loading={busy}>Create account</Button>
      </form>
    </AuthLayout>
  )
}
