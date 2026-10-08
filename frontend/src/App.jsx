import { useEffect, useState } from 'react'
import { request } from './services/api'

// Phase 2 placeholder: proves frontend → proxy → Flask → DB wiring. Replaced in Phase 11.
export default function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    request('/health')
      .then(({ data }) => setHealth(data))
      .catch(setError)
  }, [])

  return (
    <main className="min-h-screen grid place-items-center bg-slate-50 text-slate-800">
      <div className="text-center space-y-3">
        <h1 className="text-4xl font-bold text-emerald-700">FinTwin</h1>
        <p className="text-slate-500">Analyze. Predict. Simulate. Decide Better.</p>
        <p className="text-sm">
          {error && <span className="text-red-600">Backend: {error.message}</span>}
          {!error && !health && 'Checking backend…'}
          {health && (
            <span className={health.database === 'up' ? 'text-emerald-700' : 'text-amber-600'}>
              Backend {health.status} · database {health.database}
            </span>
          )}
        </p>
      </div>
    </main>
  )
}
