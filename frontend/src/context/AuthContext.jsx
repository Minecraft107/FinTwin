import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, tokenStore } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(tokenStore.get()))

  const logout = useCallback(() => {
    tokenStore.set(null)
    setUser(null)
  }, [])

  useEffect(() => {
    if (!tokenStore.get()) return
    api
      .get('/auth/me')
      .then(({ data }) => setUser(data))
      .catch(() => logout())
      .finally(() => setLoading(false))
  }, [logout])

  useEffect(() => {
    window.addEventListener('fintwin:logout', logout)
    return () => window.removeEventListener('fintwin:logout', logout)
  }, [logout])

  const startSession = useCallback(({ user, access_token }) => {
    tokenStore.set(access_token)
    setUser(user)
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      logout,
      login: async (email, password) => startSession((await api.post('/auth/login', { email, password })).data),
      register: async (body) => startSession((await api.post('/auth/register', body)).data),
      demo: async () => startSession((await api.post('/auth/demo')).data),
    }),
    [user, loading, logout, startSession],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
