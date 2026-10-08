import { useCallback, useEffect, useState } from 'react'
import { request } from '../services/api'

// GET `path` (null = don't fetch). Re-fetches when the path changes or reload() is called.
export function useApi(path) {
  const [state, setState] = useState({ data: null, meta: null, error: null, loading: Boolean(path) })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    if (!path) return undefined
    let cancelled = false
    setState((s) => ({ ...s, loading: true, error: null }))
    request(path)
      .then((res) => !cancelled && setState({ data: res.data, meta: res.meta, error: null, loading: false }))
      .catch((error) => !cancelled && setState({ data: null, meta: null, error, loading: false }))
    return () => {
      cancelled = true
    }
  }, [path, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, reload }
}
