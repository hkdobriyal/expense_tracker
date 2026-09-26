import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertCircle, CheckCircle2 } from 'lucide-react'
import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { Loading } from './components/ui'
import { api, setCsrfToken } from './lib/api'
import { SessionContext, ToastContext } from './lib/hooks'
import Login from './pages/Login'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Transactions = lazy(() => import('./pages/Transactions'))
const Accounts = lazy(() => import('./pages/Accounts'))
const Categories = lazy(() => import('./pages/Categories'))
const Budgets = lazy(() => import('./pages/Budgets'))
const Goals = lazy(() => import('./pages/Goals'))
const Bills = lazy(() => import('./pages/Bills'))
const Subscriptions = lazy(() => import('./pages/Subscriptions'))
const Recurring = lazy(() => import('./pages/Recurring'))
const Analytics = lazy(() => import('./pages/Analytics'))
const CashFlow = lazy(() => import('./pages/CashFlow'))
const NetWorth = lazy(() => import('./pages/NetWorth'))
const Reports = lazy(() => import('./pages/Reports'))
const Banks = lazy(() => import('./pages/Banks'))
const Import = lazy(() => import('./pages/Import'))
const Alerts = lazy(() => import('./pages/Alerts'))
const SettingsPage = lazy(() => import('./pages/Settings'))

function Toasts({ items }) {
  return (
    <div className="toasts" aria-live="polite">
      <AnimatePresence>
        {items.map((t) => (
          <motion.div key={t.id} className={`toast ${t.tone}`} initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10 }}>
            {t.tone === 'error' ? <AlertCircle size={17} color="var(--critical)" /> : <CheckCircle2 size={17} color="var(--success)" />}
            {t.message}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

export default function App() {
  const qc = useQueryClient()
  const [toasts, setToasts] = useState([])
  const push = useCallback((message, tone = 'info') => {
    const id = Math.random().toString(36).slice(2) // UI-only identifier, not financial data
    setToasts((t) => [...t.slice(-3), { id, message, tone }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === 'error' ? 6000 : 3200)
  }, [])
  const toast = useMemo(() => ({ show: (m) => push(m), success: (m) => push(m, 'success'), error: (m) => push(m, 'error') }), [push])

  const me = useQuery({
    queryKey: ['me'],
    queryFn: async () => { const r = await api.get('/auth/session'); return r.authenticated ? r : null },
    retry: false, staleTime: Infinity,
  })
  // Drop cached data from the previous user but keep the session query itself: clearing it
  // would detach this component's observer and the new session would never render.
  const resetCache = () => qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
  if (me.data) setCsrfToken(me.data.csrf_token)

  useEffect(() => {
    const theme = me.data?.settings?.theme || 'dark'
    const resolved = theme === 'system' ? (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : theme
    document.documentElement.dataset.theme = resolved
  }, [me.data?.settings?.theme])

  const session = useMemo(() => me.data && {
    ...me.data,
    refresh: () => qc.invalidateQueries({ queryKey: ['me'] }),
    logout: async () => {
      try { await api.post('/auth/logout') } finally {
        setCsrfToken('')
        resetCache()
        qc.setQueryData(['me'], null)
      }
    },
  }, [me.data, qc]) // eslint-disable-line react-hooks/exhaustive-deps

  const onSignedIn = (data) => {
    setCsrfToken(data.csrf_token)
    resetCache()
    qc.setQueryData(['me'], data)
  }

  let body
  if (me.isLoading) body = <div className="content"><Loading rows={6} /></div>
  else if (!session) body = <Login onSignedIn={onSignedIn} apiError={me.error} />
  else body = (
    <SessionContext.Provider value={session}>
      <Routes>
        <Route element={<Layout />}>
          {[
            ['/', Dashboard], ['/transactions', Transactions], ['/accounts', Accounts], ['/categories', Categories], ['/budgets', Budgets],
            ['/goals', Goals], ['/bills', Bills], ['/subscriptions', Subscriptions], ['/recurring', Recurring], ['/analytics', Analytics],
            ['/cash-flow', CashFlow], ['/net-worth', NetWorth], ['/reports', Reports], ['/banks', Banks], ['/import', Import],
            ['/alerts', Alerts], ['/settings', SettingsPage],
          ].map(([path, Page]) => <Route key={path} path={path} element={<Suspense fallback={<Loading rows={6} />}><Page /></Suspense>} />)}
          <Route path="*" element={<Suspense fallback={null}><Dashboard /></Suspense>} />
        </Route>
      </Routes>
    </SessionContext.Provider>
  )

  return (
    <ToastContext.Provider value={toast}>
      {body}
      <Toasts items={toasts} />
    </ToastContext.Provider>
  )
}
