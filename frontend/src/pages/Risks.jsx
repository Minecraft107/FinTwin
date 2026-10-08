import { RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { Button, Card, EmptyState, ErrorState, Loading, PageHeader, Segmented, SeverityBadge } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api } from '../services/api'
import { dateLabel, titleCase } from '../utils/format'

export default function Risks() {
  const [status, setStatus] = useState('active')
  const alerts = useApi(`/risks?status=${status}`)
  const [scanning, setScanning] = useState(false)

  async function scan() {
    setScanning(true)
    try {
      await api.post('/risks/scan')
      alerts.reload()
    } finally {
      setScanning(false)
    }
  }

  async function setAlertStatus(id, next) {
    await api.patch(`/risks/${id}`, { status: next })
    alerts.reload()
  }

  const counts = alerts.meta?.counts
  return (
    <>
      <PageHeader
        title="Risks & alerts"
        description="FinTwin checks every change for unusual transactions (statistical rule + Isolation Forest), duplicate charges, spending drift, and risky ratios. Alerts clear themselves when the condition goes away."
        action={<Button variant="secondary" loading={scanning} onClick={scan}><RefreshCw className="size-4" /> Re-scan</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented label="Show" value={status} onChange={setStatus} options={[{ value: 'active', label: 'Active' }, { value: 'dismissed', label: 'Dismissed' }, { value: 'all', label: 'All' }]} />
        {counts && (
          <span className="text-sm text-ink-3">
            {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].filter((l) => counts[l]).map((l) => `${counts[l]} ${l.toLowerCase()}`).join(' · ') || 'none'}
          </span>
        )}
      </div>
      {alerts.loading && !alerts.data ? <Loading /> : alerts.error ? <ErrorState error={alerts.error} onRetry={alerts.reload} /> : alerts.data.length === 0 ? (
        <EmptyState title={status === 'active' ? 'No active alerts' : 'Nothing here'}>Your latest data shows no risks that need attention.</EmptyState>
      ) : (
        <div className="space-y-3">
          {alerts.data.map((a) => (
            <Card key={a.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge level={a.severity} />
                    <span className="text-xs text-ink-3">{titleCase(a.type)} · detected {dateLabel(a.detected_at)}</span>
                  </div>
                  <h2 className="mt-2 font-semibold text-ink">{a.title}</h2>
                  <p className="mt-1 text-sm text-ink-2">{a.explanation}</p>
                  <p className="mt-2 text-sm"><span className="font-medium text-ink">What you could do: </span><span className="text-ink-2">{a.recommended_action}</span></p>
                  {a.transaction_id && <Link to="/transactions" className="mt-2 inline-block text-xs font-medium text-brand-700">Review transactions →</Link>}
                </div>
                {a.status === 'active'
                  ? <Button variant="ghost" onClick={() => setAlertStatus(a.id, 'dismissed')}>Dismiss</Button>
                  : <Button variant="ghost" onClick={() => setAlertStatus(a.id, 'active')}>Restore</Button>}
              </div>
            </Card>
          ))}
        </div>
      )}
    </>
  )
}
