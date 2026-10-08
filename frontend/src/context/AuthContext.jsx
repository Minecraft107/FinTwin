import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, tokenStore } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(tokenStore.get()))
  // Set when the session can't be checked (server down): the token is kept so a retry works.
  const [sessionError, setSessionError] = useState(null)

  const logout = useCallback(() => {
    tokenStore.set(null)
    setUser(null)
    setSessionError(null)
  }, [])

  // Only a 401 means the token is bad; anything else must not log the user out.
  const fetchMe = useCallback(
    () =>
      api
        .get('/auth/me')
        .then(({ data }) => setUser(data))
        .catch((err) => (err.status === 401 ? logout() : setSessionError(err)))
        .finally(() => setLoading(false)),
    [logout],
  )

  useEffect(() => {
    if (tokenStore.get()) fetchMe()
  }, [fetchMe])

  const retrySession = useCallback(() => {
    setSessionError(null)
    setLoading(true)
    fetchMe()
  }, [fetchMe])

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
      sessionError,
      retrySession,
      logout,
      login: async (email, password) => startSession((await api.post('/auth/login', { email, password })).data),
      register: async (body) => startSession((await api.post('/auth/register', body)).data),
      demo: async () => startSession((await api.post('/auth/demo')).data),
    }),
    [user, loading, sessionError, retrySession, logout, startSession],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
