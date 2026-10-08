import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'
import { ErrorState, Loading } from './components/ui'
import { useAuth } from './context/AuthContext'
import AppShell from './layouts/AppShell'
import { Login, Register } from './pages/Auth'
import Landing from './pages/Landing'

// App pages load on demand, so the landing and login screens don't download the chart library.
const Dashboard = lazy(() => import('./pages/Dashboard'))
const DigitalTwin = lazy(() => import('./pages/DigitalTwin'))
const Transactions = lazy(() => import('./pages/Transactions'))
const Analytics = lazy(() => import('./pages/Analytics'))
const Forecasts = lazy(() => import('./pages/Forecasts'))
const Goals = lazy(() => import('./pages/Goals'))
const Simulator = lazy(() => import('./pages/Simulator'))
const Risks = lazy(() => import('./pages/Risks'))
const Coach = lazy(() => import('./pages/Coach'))
const Profile = lazy(() => import('./pages/Profile'))

function RequireAuth({ children }) {
  const { user, loading, sessionError, retrySession } = useAuth()
  const location = useLocation()
  if (loading) return <Loading label="Restoring your session…" />
  if (sessionError) return <div className="mx-auto max-w-md p-6"><ErrorState error={sessionError} onRetry={retrySession} /></div>
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return children
}

function GuestOnly({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  return user ? <Navigate to="/dashboard" replace /> : children
}

const page = (Component) => (
  <Suspense fallback={<Loading />}>
    <Component />
  </Suspense>
)

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route path="/dashboard" element={page(Dashboard)} />
        <Route path="/twin" element={page(DigitalTwin)} />
        <Route path="/transactions" element={page(Transactions)} />
        <Route path="/analytics" element={page(Analytics)} />
        <Route path="/forecasts" element={page(Forecasts)} />
        <Route path="/goals" element={page(Goals)} />
        <Route path="/simulator" element={page(Simulator)} />
        <Route path="/risks" element={page(Risks)} />
        <Route path="/coach" element={page(Coach)} />
        <Route path="/profile" element={page(Profile)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
