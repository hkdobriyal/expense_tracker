import React, { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { deleteResource, deleteTransaction, fetchWorkspace, restoreBackup, saveResource, saveTransaction } from './lib/api'
import { API, accountTypes, categories, navItems } from './lib/constants'
import { categoryColor, daysUntil, inMonth, lastMonths, longDate, money, monthKey } from './lib/format'
import {
  BackgroundParticles,
  CaptureForm,
  ConfirmDialog,
  DonutChart,
  Icon,
  MetricCards,
  MonthChips,
  PageIntro,
  PanelHeading,
  SettingRow,
  SpendingBars,
  TransactionRow,
  TrendChart,
} from './components/ui'
import { ThreeDCore } from './components/ThreeDCore'
import { AutoSyncHub } from './components/AutoSyncHub'
import { playChime, playClick, isSoundEnabled, setSoundEnabled } from './lib/sound'

const emptyForm = () => ({
  title: '',
  amount: '',
  category: 'Groceries',
  notes: '',
  kind: 'expense',
  payment_method: 'UPI',
  merchant: '',
  date: new Date().toISOString().slice(0, 10),
  recurring: false,
})

const emptyResource = () => ({
  name: '',
  amount: '',
  category: 'Groceries',
  institution: '',
  due_date: '',
  target_amount: '',
  current_amount: '0',
  period: 'monthly',
  account_type: 'savings',
  status: 'upcoming',
  target_date: '',
})

export default function App() {
  const [items, setItems] = useState([])
  const [activeView, setActiveView] = useState('overview')
  const [form, setForm] = useState(emptyForm)
  const [showCapture, setShowCapture] = useState(false)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('All')
  const [kindFilter, setKindFilter] = useState('all')
  const [month, setMonth] = useState(monthKey())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')
  const [accounts, setAccounts] = useState([])
  const [budgets, setBudgets] = useState([])
  const [goals, setGoals] = useState([])
  const [bills, setBills] = useState([])
  const [advancedAnalytics, setAdvancedAnalytics] = useState(null)
  const [soundActive, setSoundActive] = useState(isSoundEnabled())
  const [resourceModal, setResourceModal] = useState('')
  const [resourceForm, setResourceForm] = useState(emptyResource)
  const [motionEnabled, setMotionEnabled] = useState(true)
  const [editingTransaction, setEditingTransaction] = useState(null)
  const [editingResource, setEditingResource] = useState(null)
  const [cursor, setCursor] = useState({ x: 0, y: 0, visible: false })
  const [confirm, setConfirm] = useState(null)
  const [commandOpen, setCommandOpen] = useState(false)
  const [commandQuery, setCommandQuery] = useState('')
  const restoreInput = useRef(null)
  const months = useMemo(() => lastMonths(8), [])
  const particles = useMemo(() => Array.from({ length: 28 }, (_, index) => ({
    id: index,
    left: `${(index * 17) % 100}%`,
    top: `${(index * 23) % 100}%`,
    size: 4 + (index % 4),
    delay: (index % 6) * 0.4,
    duration: 10 + (index % 7) * 2.5,
    opacity: 0.28 + (index % 5) * 0.12,
  })), [])

  async function loadWorkspace() {
    try {
      setError('')
      const data = await fetchWorkspace()
      setItems(data.transactions)
      setAccounts(data.accounts)
      setBudgets(data.budgets)
      setGoals(data.goals)
      setBills(data.bills)
      if (data.analytics) setAdvancedAnalytics(data.analytics)
    } catch {
      setError('The API is unavailable. Start FastAPI on port 8000 and refresh.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadWorkspace() }, [])
  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(() => setToast(''), 2600)
    return () => clearTimeout(timer)
  }, [toast])

  useEffect(() => {
    const handlePointerMove = (event) => setCursor({ x: event.clientX, y: event.clientY, visible: event.pointerType === 'mouse' })
    const handlePointerLeave = () => setCursor((current) => ({ ...current, visible: false }))
    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerleave', handlePointerLeave)
    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerleave', handlePointerLeave)
    }
  }, [])

  useEffect(() => {
    const onKey = (event) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setCommandOpen((open) => !open)
        setCommandQuery('')
      }
      if (event.key === 'Escape') {
        setShowCapture(false)
        setResourceModal('')
        setCommandOpen(false)
        setConfirm(null)
      }
      if (!typing && event.key.toLowerCase() === 'n') openCapture()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function openCapture(kind = 'expense') {
    setEditingTransaction(null)
    setForm({ ...emptyForm(), kind })
    setShowCapture(true)
  }

  function closeCapture() {
    setShowCapture(false)
    setEditingTransaction(null)
    setForm(emptyForm())
  }

  async function addTransaction(event) {
    event.preventDefault()
    if (!form.title.trim() || !form.amount || Number(form.amount) <= 0) {
      setToast('Enter the required name and amount')
      return
    }
    try {
      setSaving(true)
      setError('')
      const payload = { ...form, amount: Number(form.amount), date: form.date ? `${form.date}T12:00:00` : undefined }
      const response = await saveTransaction(payload, editingTransaction?.id)
      setItems((current) => (editingTransaction ? current.map((item) => (item.id === editingTransaction.id ? response.data : item)) : [response.data, ...current]))
      closeCapture()
      setToast(editingTransaction ? 'Transaction updated' : 'Added to your ledger')
    } catch {
      setError('Could not save this transaction. Check that the API is running.')
    } finally {
      setSaving(false)
    }
  }

  function requestDeleteTransaction(item) {
    setConfirm({
      title: 'Remove this transaction?',
      copy: `${item.title} · ${money(item.amount)} will leave your ledger.`,
      confirmLabel: 'Delete',
      run: async () => {
        try {
          await deleteTransaction(item.id)
          setItems((current) => current.filter((entry) => entry.id !== item.id))
          setToast('Transaction removed')
        } catch {
          setError('Could not remove that transaction.')
        }
      },
    })
  }

  async function createResource(event) {
    event.preventDefault()
    const route = resourceModal === 'account' ? 'accounts' : resourceModal === 'budget' ? 'budgets' : resourceModal === 'goal' ? 'goals' : 'bills'
    const payload = resourceModal === 'account'
      ? { name: resourceForm.name, account_type: resourceForm.account_type, institution: resourceForm.institution, opening_balance: Number(resourceForm.amount) || 0 }
      : resourceModal === 'budget'
        ? { name: resourceForm.name, category: resourceForm.category, amount: Number(resourceForm.amount), period: resourceForm.period }
        : resourceModal === 'goal'
          ? { name: resourceForm.name, target_amount: Number(resourceForm.target_amount), current_amount: Number(resourceForm.current_amount) || 0, target_date: resourceForm.target_date || null }
          : { name: resourceForm.name, amount: Number(resourceForm.amount), due_date: resourceForm.due_date, frequency: resourceForm.period, status: resourceForm.status || 'upcoming' }
    const amountRequired = ['budget', 'bill'].includes(resourceModal)
    if (!resourceForm.name.trim() || (amountRequired && (!resourceForm.amount || Number(resourceForm.amount) <= 0)) || (resourceModal === 'goal' && (!resourceForm.target_amount || Number(resourceForm.target_amount) <= 0)) || (resourceModal === 'bill' && !resourceForm.due_date)) {
      setToast('Fill the fields marked required')
      return
    }
    try {
      const response = await saveResource(route, payload, editingResource?.id)
      const setter = resourceModal === 'account' ? setAccounts : resourceModal === 'budget' ? setBudgets : resourceModal === 'goal' ? setGoals : setBills
      setter((current) => (editingResource ? current.map((item) => (item.id === editingResource.id ? response.data : item)) : [response.data, ...current]))
      setResourceModal('')
      setEditingResource(null)
      setResourceForm(emptyResource())
      setToast(`${resourceModal} ${editingResource ? 'updated' : 'created'}`)
    } catch {
      setError(`Could not save this ${resourceModal}.`)
    }
  }

  function editTransaction(item) {
    setEditingTransaction(item)
    setForm({
      title: item.title,
      amount: item.amount,
      category: item.category || 'Groceries',
      notes: item.notes || '',
      kind: item.kind || 'expense',
      payment_method: item.payment_method || 'UPI',
      merchant: item.merchant || '',
      date: item.date ? String(item.date).slice(0, 10) : new Date().toISOString().slice(0, 10),
      recurring: Boolean(item.recurring),
    })
    setShowCapture(true)
  }

  function editResource(type, item) {
    if (type === 'investment') {
      editTransaction(item)
      return
    }
    setEditingResource(item)
    setResourceModal(type)
    setResourceForm({
      name: item.name || '',
      amount: item.amount || item.opening_balance || '',
      category: item.category || 'Groceries',
      institution: item.institution || '',
      due_date: item.due_date || '',
      target_amount: item.target_amount || '',
      current_amount: item.current_amount || '0',
      period: item.period || item.frequency || 'monthly',
      account_type: item.account_type || 'savings',
      status: item.status || 'upcoming',
      target_date: item.target_date || '',
    })
  }

  function requestDeleteResource(type, item) {
    if (type === 'investment') {
      requestDeleteTransaction(item)
      return
    }
    const route = type === 'account' ? 'accounts' : `${type}s`
    setConfirm({
      title: `Remove this ${type}?`,
      copy: `${item.name || item.title} will be deleted from your workspace.`,
      confirmLabel: 'Delete',
      run: async () => {
        try {
          await deleteResource(route, item.id)
          const setter = type === 'account' ? setAccounts : type === 'budget' ? setBudgets : type === 'goal' ? setGoals : setBills
          setter((current) => current.filter((entry) => entry.id !== item.id))
          setToast(`${type} removed`)
        } catch {
          setError(`Could not remove this ${type}.`)
        }
      },
    })
  }

  async function markBillPaid(bill) {
    try {
      const response = await saveResource('bills', { name: bill.name, amount: bill.amount, due_date: bill.due_date, frequency: bill.frequency, status: 'paid' }, bill.id)
      setBills((current) => current.map((item) => (item.id === bill.id ? response.data : item)))
      setToast('Bill marked as paid')
    } catch {
      setError('Could not update this bill.')
    }
  }

  async function onRestoreFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const payload = JSON.parse(await file.text())
      setConfirm({
        title: 'Replace this workspace?',
        copy: 'Restoring a backup overwrites transactions, accounts, budgets, goals, and bills on this device.',
        confirmLabel: 'Restore backup',
        run: async () => {
          await restoreBackup(payload)
          await loadWorkspace()
          setToast('Backup restored')
        },
      })
    } catch {
      setToast('That file is not a valid Ledgerly backup')
    }
  }

  const scopedItems = useMemo(() => items.filter((item) => inMonth(item.date, month)), [items, month])
  const expenses = useMemo(() => scopedItems.filter((item) => (item.kind || 'expense') === 'expense').reduce((sum, item) => sum + Number(item.amount), 0), [scopedItems])
  const income = useMemo(() => scopedItems.filter((item) => item.kind === 'income').reduce((sum, item) => sum + Number(item.amount), 0), [scopedItems])
  const investments = useMemo(() => scopedItems.filter((item) => item.kind === 'investment').reduce((sum, item) => sum + Number(item.amount), 0), [scopedItems])
  const cashflow = income - expenses
  const savingsRate = income ? Math.round(((income - expenses - investments) / income) * 100) : 0
  const accountTotal = accounts.reduce((sum, item) => sum + Number(item.opening_balance || 0), 0)
  const billsDue = bills.filter((bill) => bill.status !== 'paid').reduce((sum, bill) => sum + Number(bill.amount || 0), 0)
  const breakdown = useMemo(() => categories.map((category) => ({
    category,
    amount: scopedItems.filter((item) => (item.kind || 'expense') === 'expense' && item.category === category).reduce((sum, item) => sum + Number(item.amount), 0),
    color: categoryColor(category),
  })).filter((item) => item.amount > 0).sort((a, b) => b.amount - a.amount), [scopedItems])
  const maxCategory = Math.max(...breakdown.map((item) => item.amount), 1)
  const filteredItems = useMemo(() => items.filter((item) => {
    const matchesMonth = inMonth(item.date, month)
    const matchesCategory = filter === 'All' || item.category === filter
    const matchesKind = kindFilter === 'all' || (item.kind || 'expense') === kindFilter
    const haystack = `${item.title} ${item.category} ${item.notes || ''} ${item.merchant || ''} ${item.payment_method || ''}`.toLowerCase()
    return matchesMonth && matchesCategory && matchesKind && haystack.includes(query.toLowerCase())
  }), [items, filter, query, kindFilter, month])
  const trend = useMemo(() => months.map((key) => ({
    month: key,
    expense: items.filter((item) => (item.kind || 'expense') === 'expense' && inMonth(item.date, key)).reduce((sum, item) => sum + Number(item.amount), 0),
    income: items.filter((item) => item.kind === 'income' && inMonth(item.date, key)).reduce((sum, item) => sum + Number(item.amount), 0),
  })), [items, months])
  const budgetCards = budgets.map((budget) => {
    const spent = items.filter((item) => (item.kind || 'expense') === 'expense' && item.category === budget.category && (budget.period !== 'monthly' || inMonth(item.date, month === 'all' ? monthKey() : month))).reduce((sum, item) => sum + Number(item.amount), 0)
    const limit = Number(budget.amount) || 1
    return { ...budget, spent, progress: Math.min(100, Math.round((spent / limit) * 100)) }
  })
  const commandResults = useMemo(() => {
    const navigation = navItems.filter((item) => item.label.toLowerCase().includes(commandQuery.toLowerCase()))
    const matches = items.filter((item) => `${item.title} ${item.merchant || ''}`.toLowerCase().includes(commandQuery.toLowerCase())).slice(0, 6)
    return { navigation, matches }
  }, [commandQuery, items])

  return (
    <div className={`app-shell ${motionEnabled ? '' : 'motion-disabled'}`}>
      <BackgroundParticles particles={particles} />
      <div className={`cursor-glow ${cursor.visible ? 'visible' : ''}`} style={{ left: cursor.x, top: cursor.y }} />
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">+</span><span>ledgerly</span></div>
        <div className="sidebar-label">WORKSPACE</div>
        <nav>
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`nav-item ${activeView === item.id ? 'active' : ''}`}
              onClick={() => {
                playClick()
                setActiveView(item.id)
              }}
            >
              <Icon name={item.id}>{item.icon}</Icon>
              {item.label}
              {item.id === 'transactions' && items.length > 0 && <small>{items.length}</small>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button className="command-hint" onClick={() => { playClick(); setCommandOpen(true) }}>Search · Ctrl K</button>
          <button className="nav-item" onClick={() => { playClick(); setActiveView('settings') }}><Icon name="settings">⚙</Icon>Settings</button>
          <div className="profile-card">
            <span className="avatar">H</span>
            <div>
              <strong>Personal space</strong>
              <span>Local workspace</span>
            </div>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button className="mobile-brand brand" onClick={() => { playClick(); setActiveView('overview') }}><span className="brand-mark">+</span><span>ledgerly</span></button>
          <div className="topbar-title">{navItems.find((item) => item.id === activeView)?.label || 'Settings'}</div>
          <div className="topbar-actions">
            <button className="icon-button notification" onClick={() => { playClick(); setCommandOpen(true) }} aria-label="Search">⌕</button>
            <button className="top-add" onClick={() => { playClick(); openCapture() }}>+ <span>Add transaction</span></button>
          </div>
        </header>
        <main className="dashboard">
          {error && <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="error-banner">{error} <button className="text-button" onClick={loadWorkspace}>Retry</button></motion.div>}
          <AnimatePresence mode="wait">
            {activeView === 'overview' && (
              <motion.div key="overview" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <section className="intro-row">
                  <div>
                    <p className="eyebrow">{longDate()} · INDIA</p>
                    <h1>Your money, <em>in motion.</em></h1>
                    <p className="intro-copy">Track every rupee, from UPI chai runs to long-term investments.</p>
                    <MonthChips months={months.slice(-4)} value={month} onChange={(m) => { playClick(); setMonth(m) }} />
                  </div>
                  <ThreeDCore cashflow={cashflow} invested={investments} billsDue={billsDue} />
                </section>
                <MetricCards
                  expenses={expenses}
                  income={income}
                  investments={investments}
                  cashflow={cashflow}
                  count={scopedItems.length}
                  healthScore={advancedAnalytics?.financial_health_score}
                  burnRate={advancedAnalytics?.daily_burn_rate}
                />
                <section className="pulse-row">
                  <div className="pulse-chip"><span>Savings rate</span><strong>{savingsRate}%</strong></div>
                  <div className="pulse-chip"><span>Accounts</span><strong>{money(accountTotal)}</strong></div>
                  <div className="pulse-chip"><span>Open bills</span><strong>{money(billsDue)}</strong></div>
                  <div className="pulse-chip"><span>Daily burn</span><strong>{money(advancedAnalytics?.daily_burn_rate || 0)}/d</strong></div>
                </section>
                <section className="content-grid">
                  <motion.div className="panel add-panel">
                    <div className="panel-heading">
                      <div>
                        <span className="section-kicker">QUICK CAPTURE</span>
                        <h2>Add a transaction</h2>
                      </div>
                      <span className="plus-icon">+</span>
                    </div>
                    <CaptureForm form={form} setForm={setForm} onSubmit={addTransaction} saving={saving} editing={false} autoFocus={false} />
                  </motion.div>
                  <motion.div className="panel breakdown-panel">
                    <PanelHeading kicker="WHERE IT GOES" title="Spending mix" action={month === 'all' ? 'All time' : 'This period'} />
                    <DonutChart breakdown={breakdown} />
                    <SpendingBars breakdown={breakdown} maxCategory={maxCategory} />
                  </motion.div>
                </section>
                <section className="panel activity-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="section-kicker">LIVE LEDGER</span>
                      <h2>Recent activity</h2>
                    </div>
                    <button className="text-button" onClick={() => { playClick(); setActiveView('transactions') }}>View all ↗</button>
                  </div>
                  {loading ? <div className="empty-state">Loading your ledger...</div> : scopedItems.slice(0, 6).length ? (
                    <div className="transaction-list">
                      <AnimatePresence initial={false}>
                        {scopedItems.slice(0, 6).map((item) => (
                          <TransactionRow key={item.id} item={item} onDelete={requestDeleteTransaction} onEdit={editTransaction} />
                        ))}
                      </AnimatePresence>
                    </div>
                  ) : (
                    <div className="empty-state">
                      <span className="empty-orbit">+</span>
                      <h3>Nothing recorded yet</h3>
                      <p>Add your first expense or test 1-click UPI sync to watch your dashboard come alive.</p>
                    </div>
                  )}
                </section>
              </motion.div>
            )}
            {activeView === 'autosync' && (
              <motion.div key="autosync" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <AutoSyncHub
                  advancedAnalytics={advancedAnalytics}
                  onTransactionAdded={(txn) => {
                    loadWorkspace()
                    setToast(txn ? `Synced: ${txn.title} · ${money(txn.amount)}` : 'Workspace updated')
                    playChime()
                  }}
                />
              </motion.div>
            )}

            {activeView === 'transactions' && (
              <motion.div key="transactions" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <PageIntro kicker="YOUR LEDGER" title="Every rupee, accounted for." copy="Search, filter by month and type, edit, and keep a clean financial history." action={<button className="primary-button compact" onClick={() => openCapture()}>+ Add transaction</button>} />
                <MonthChips months={months} value={month} onChange={setMonth} />
                <div className="panel transactions-panel">
                  <div className="toolbar">
                    <div className="search-box">⌕<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, merchant, notes" /></div>
                    <select value={kindFilter} onChange={(event) => setKindFilter(event.target.value)}>
                      <option value="all">All types</option>
                      <option value="expense">Expenses</option>
                      <option value="income">Income</option>
                      <option value="investment">Investments</option>
                    </select>
                    <select value={filter} onChange={(event) => setFilter(event.target.value)}>
                      <option>All</option>
                      {categories.map((category) => <option key={category}>{category}</option>)}
                    </select>
                  </div>
                  <div className="transaction-table-head"><span>DESCRIPTION</span><span>DATE</span><span>AMOUNT</span><span>ACTIONS</span></div>
                  {loading ? <div className="empty-state">Loading your ledger...</div> : filteredItems.length ? (
                    <div className="transaction-list">
                      <AnimatePresence>{filteredItems.map((item) => <TransactionRow key={item.id} item={item} onDelete={requestDeleteTransaction} onEdit={editTransaction} />)}</AnimatePresence>
                    </div>
                  ) : (
                    <div className="empty-state"><span className="empty-orbit">⌕</span><h3>No transactions found</h3><p>Try another search or add a new entry.</p></div>
                  )}
                </div>
              </motion.div>
            )}
            {activeView === 'insights' && (
              <motion.div key="insights" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <PageIntro kicker="PATTERNS & SIGNALS" title="See the shape of your spending." copy="Small patterns become useful decisions when you can see them clearly." />
                <MonthChips months={months.slice(-4)} value={month} onChange={setMonth} />
                <MetricCards expenses={expenses} income={income} investments={investments} cashflow={cashflow} count={scopedItems.length} />
                <section className="insights-grid">
                  <div className="panel">
                    <PanelHeading kicker="CATEGORY PULSE" title="Where your money goes" action={month === 'all' ? 'All time' : 'This period'} />
                    <DonutChart breakdown={breakdown} />
                    <SpendingBars breakdown={breakdown} maxCategory={maxCategory} />
                  </div>
                  <div className="panel">
                    <PanelHeading kicker="EIGHT MONTH VIEW" title="Income vs spend" />
                    <TrendChart series={trend} />
                  </div>
                  <div className="panel insight-callout">
                    <span className="insight-symbol">✦</span>
                    <span className="section-kicker">A LITTLE SIGNAL</span>
                    <h2>{breakdown[0] ? `${breakdown[0].category} is your biggest category.` : 'Your story starts with one entry.'}</h2>
                    <p>{breakdown[0] ? `${money(breakdown[0].amount)} has gone there in this view. Keep tracking for a clearer monthly rhythm.` : 'Add a few transactions and Ledgerly will surface useful patterns here.'}</p>
                    <p className="insight-note">Savings rate {savingsRate}% · cashflow {money(cashflow)}</p>
                    <button className="ghost-button" onClick={() => openCapture()}>Capture something <span>↗</span></button>
                  </div>
                </section>
              </motion.div>
            )}
            {activeView === 'accounts' && (
              <ResourceView key="accounts" kicker="YOUR MONEY PLACES" title="Accounts, wallets, and cards." copy="Keep savings, cash, wallets, and investment accounts visible." items={accounts} empty="No accounts yet. Add your first bank account." type="account" onAdd={() => { setEditingResource(null); setResourceForm(emptyResource()); setResourceModal('account') }} onEdit={editResource} onDelete={requestDeleteResource} />
            )}
            {activeView === 'investments' && (
              <ResourceView key="investments" kicker="BUILDING WEALTH" title="Your investment universe." copy="Investments stay separate from everyday spending so net worth stays meaningful." items={items.filter((item) => item.kind === 'investment')} empty="No investments recorded yet. Use Investment in Quick Capture." type="investment" onAdd={() => openCapture('investment')} onEdit={editResource} onDelete={requestDeleteResource} />
            )}
            {activeView === 'budgets' && (
              <motion.div key="budgets" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <PageIntro kicker="SPEND WITH INTENTION" title="Budgets that feel alive." copy="Each card compares this period’s actual spend against the limit you set." action={<button className="primary-button compact" onClick={() => { setEditingResource(null); setResourceForm(emptyResource()); setResourceModal('budget') }}>+ Add budget</button>} />
                <div className="resource-grid">
                  {budgetCards.length ? budgetCards.map((budget) => (
                    <motion.div className={`resource-card panel budget-card ${budget.progress >= 100 ? 'over' : ''}`} key={budget.id} whileHover={{ y: -4 }}>
                      <span className="resource-icon">◒</span>
                      <span className="section-kicker">{budget.category} · {budget.period}</span>
                      <h2>{budget.name}</h2>
                      <strong>{money(budget.spent)} <small>/ {money(budget.amount)}</small></strong>
                      <div className="goal-progress"><motion.div initial={{ width: 0 }} animate={{ width: `${budget.progress}%` }} style={{ background: budget.progress >= 100 ? '#ff8fab' : '#8ae6ff' }} /></div>
                      <p>{budget.progress}% of limit used this period</p>
                      <div className="card-actions">
                        <button onClick={() => editResource('budget', budget)}>Edit</button>
                        <button onClick={() => requestDeleteResource('budget', budget)}>Delete</button>
                      </div>
                    </motion.div>
                  )) : (
                    <div className="panel empty-resource"><span className="empty-orbit">+</span><h3>No budgets created yet.</h3><button className="ghost-button" onClick={() => setResourceModal('budget')}>Create budget <span>↗</span></button></div>
                  )}
                </div>
              </motion.div>
            )}
            {activeView === 'bills' && (
              <motion.div key="bills" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <PageIntro kicker="NEVER MISS A DUE DATE" title="Bills and recurring commitments." copy="Rent, EMIs, subscriptions, insurance, and SIPs belong here." action={<button className="primary-button compact" onClick={() => { setEditingResource(null); setResourceForm(emptyResource()); setResourceModal('bill') }}>+ Add bill</button>} />
                <div className="resource-grid">
                  {bills.length ? bills.map((bill) => {
                    const due = daysUntil(bill.due_date)
                    return (
                      <motion.div className={`resource-card panel ${bill.status === 'paid' ? 'paid' : due < 0 ? 'overdue' : ''}`} key={bill.id} whileHover={{ y: -4 }}>
                        <span className="resource-icon">◷</span>
                        <span className="section-kicker">{bill.status === 'paid' ? 'PAID' : due < 0 ? 'OVERDUE' : due === 0 ? 'DUE TODAY' : `${due} DAYS LEFT`}</span>
                        <h2>{bill.name}</h2>
                        <strong>{money(bill.amount)}</strong>
                        <p>{bill.due_date} · {bill.frequency}</p>
                        <div className="card-actions">
                          {bill.status !== 'paid' && <button onClick={() => markBillPaid(bill)}>Mark paid</button>}
                          <button onClick={() => editResource('bill', bill)}>Edit</button>
                          <button onClick={() => requestDeleteResource('bill', bill)}>Delete</button>
                        </div>
                      </motion.div>
                    )
                  }) : (
                    <div className="panel empty-resource"><span className="empty-orbit">+</span><h3>No upcoming bills yet.</h3><button className="ghost-button" onClick={() => setResourceModal('bill')}>Create bill <span>↗</span></button></div>
                  )}
                </div>
              </motion.div>
            )}
            {activeView === 'goals' && (
              <motion.div key="goals" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <PageIntro kicker="YOUR NORTH STAR" title="Make room for what matters." copy="Goals turn good intentions into visible progress." action={<button className="primary-button compact" onClick={() => { setEditingResource(null); setResourceForm(emptyResource()); setResourceModal('goal') }}>+ Create goal</button>} />
                <section className="goals-grid">
                  {goals.length ? goals.map((goal) => {
                    const progress = Math.min(100, Math.round((Number(goal.current_amount) / Number(goal.target_amount || 1)) * 100))
                    return (
                      <motion.div className="goal-card panel" key={goal.id} whileHover={{ y: -5 }}>
                        <div className="goal-icon" style={{ color: '#70d6ff' }}>◎</div>
                        <span className="section-kicker">SAVING TOWARD</span>
                        <h2>{goal.name}</h2>
                        <strong>{money(goal.current_amount)} <small>/ {money(goal.target_amount)}</small></strong>
                        <div className="goal-progress"><motion.div initial={{ width: 0 }} animate={{ width: `${progress}%` }} style={{ background: '#70d6ff' }} /></div>
                        <div className="goal-foot"><span>{progress}% complete</span><span>{goal.target_date || 'Keep going'}</span></div>
                        <div className="card-actions">
                          <button onClick={() => editResource('goal', goal)}>Edit</button>
                          <button onClick={() => requestDeleteResource('goal', goal)}>Delete</button>
                        </div>
                      </motion.div>
                    )
                  }) : (
                    <div className="panel empty-resource"><span className="empty-orbit">◎</span><h3>No goals yet. Give your next idea a place to grow.</h3></div>
                  )}
                  <button className="new-goal-card" onClick={() => { setEditingResource(null); setResourceForm(emptyResource()); setResourceModal('goal') }}>
                    <span>+</span><strong>Create a goal</strong><small>Emergency fund, trip, or home</small>
                  </button>
                </section>
              </motion.div>
            )}
            {activeView === 'settings' && (
              <motion.div key="settings" className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
                <PageIntro kicker="YOUR SPACE" title="Make Ledgerly yours." copy="A few quiet controls for the way you like to work." />
                <div className="settings-grid">
                  <div className="panel settings-panel">
                    <SettingRow title="Currency" description="Used across your dashboard" value="INR · ₹" />
                    <SettingRow title="Workspace" description="Your data stays on this device" value="Local only" />
                    <SettingRow
                      title="Audio Feedback"
                      description="Futuristic clicks and celebratory sync chimes"
                      value={soundActive ? 'On' : 'Off'}
                      toggle
                      active={soundActive}
                      onToggle={() => {
                        const next = !soundActive
                        setSoundActive(next)
                        setSoundEnabled(next)
                        if (next) playChime()
                        setToast(`Audio ${next ? 'enabled' : 'muted'}`)
                      }}
                    />
                    <SettingRow title="Export CSV" description="Spreadsheet backup for transactions" value={<button className="export-button" onClick={() => { window.location.href = `${API}/transactions/export.csv` }}>CSV ↓</button>} />
                    <SettingRow title="Full backup" description="JSON backup for every finance module" value={<button className="export-button" onClick={() => { window.location.href = `${API}/backup.json` }}>JSON ↓</button>} />
                    <SettingRow title="Restore backup" description="Replace this workspace from a JSON file" value={<button className="export-button" onClick={() => restoreInput.current?.click()}>JSON ↑</button>} />
                    <SettingRow title="Motion" description="Animated transitions and surfaces" value={motionEnabled ? 'On' : 'Off'} toggle active={motionEnabled} onToggle={() => { setMotionEnabled(!motionEnabled); setToast(`Motion ${motionEnabled ? 'disabled' : 'enabled'}`) }} />
                    <input ref={restoreInput} type="file" accept="application/json" hidden onChange={onRestoreFile} />
                  </div>
                  <div className="panel appearance-panel">
                    <span className="section-kicker">INDIA READY</span>
                    <h2>Built for rupees.</h2>
                    <p>Capture UPI, cash, cards, bank transfers, investments, recurring bills, and daily spending in one private workspace. Press N to add, Ctrl+K to search.</p>
                    <div className="theme-swatches"><i /><i /><i /><i /></div>
                    <button className="ghost-button" onClick={() => setToast('Your data stays local on this device')}>Local-first <span>✓</span></button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
      <div className="mobile-nav">
        {navItems.map((item) => (
          <button className={activeView === item.id ? 'active' : ''} key={item.id} onClick={() => setActiveView(item.id)}>
            <span>{item.icon}</span>{item.label}
          </button>
        ))}
      </div>
      <AnimatePresence>
        {showCapture && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={closeCapture}>
            <motion.div className="capture-modal" initial={{ y: 30, opacity: 0, scale: 0.97 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 30, opacity: 0 }} onClick={(event) => event.stopPropagation()}>
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">QUICK CAPTURE</span>
                  <h2>{editingTransaction ? 'Edit transaction' : 'Add a transaction'}</h2>
                </div>
                <button className="icon-button close-button" onClick={closeCapture}>×</button>
              </div>
              <CaptureForm form={form} setForm={setForm} onSubmit={addTransaction} saving={saving} editing={Boolean(editingTransaction)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {resourceModal && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setResourceModal('')}>
            <motion.div className="capture-modal resource-modal" initial={{ y: 30, opacity: 0, scale: 0.97 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 30, opacity: 0 }} onClick={(event) => event.stopPropagation()}>
              <div className="panel-heading">
                <div>
                  <span className="section-kicker">{editingResource ? 'EDIT' : 'NEW'} {resourceModal.toUpperCase()}</span>
                  <h2>{editingResource ? 'Update' : 'Create'} {resourceModal}</h2>
                </div>
                <button className="icon-button close-button" onClick={() => setResourceModal('')}>×</button>
              </div>
              <form className="capture-form" onSubmit={createResource}>
                <label>Name <span className="required">required</span><input autoFocus required value={resourceForm.name} onChange={(event) => setResourceForm({ ...resourceForm, name: event.target.value })} placeholder={resourceModal === 'bill' ? 'e.g. Electricity bill' : `e.g. ${resourceModal} name`} /></label>
                {resourceModal === 'account' && (
                  <div className="form-row">
                    <label>Type<select value={resourceForm.account_type} onChange={(event) => setResourceForm({ ...resourceForm, account_type: event.target.value })}>{accountTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
                    <label>Bank or institution<input value={resourceForm.institution} onChange={(event) => setResourceForm({ ...resourceForm, institution: event.target.value })} placeholder="e.g. HDFC Bank" /></label>
                  </div>
                )}
                {resourceModal === 'budget' && (
                  <div className="form-row">
                    <label>Category<select value={resourceForm.category} onChange={(event) => setResourceForm({ ...resourceForm, category: event.target.value })}>{categories.map((category) => <option key={category}>{category}</option>)}</select></label>
                    <label>Period<select value={resourceForm.period} onChange={(event) => setResourceForm({ ...resourceForm, period: event.target.value })}><option>monthly</option><option>weekly</option><option>yearly</option></select></label>
                  </div>
                )}
                {resourceModal === 'goal' ? (
                  <>
                    <div className="form-row">
                      <label>Target in INR <span className="required">required</span><input type="number" min="1" required value={resourceForm.target_amount} onChange={(event) => setResourceForm({ ...resourceForm, target_amount: event.target.value })} /></label>
                      <label>Already saved<input type="number" min="0" value={resourceForm.current_amount} onChange={(event) => setResourceForm({ ...resourceForm, current_amount: event.target.value })} /></label>
                    </div>
                    <label>Target date <span className="optional">optional</span><input type="date" value={resourceForm.target_date} onChange={(event) => setResourceForm({ ...resourceForm, target_date: event.target.value })} /></label>
                  </>
                ) : (
                  <label>{resourceModal === 'account' ? 'Opening balance in INR' : <>Amount in INR <span className="required">required</span></>}<input type="number" min="0" value={resourceForm.amount} onChange={(event) => setResourceForm({ ...resourceForm, amount: event.target.value })} /></label>
                )}
                {resourceModal === 'bill' && (
                  <div className="form-row">
                    <label>Due date <span className="required">required</span><input type="date" required value={resourceForm.due_date} onChange={(event) => setResourceForm({ ...resourceForm, due_date: event.target.value })} /></label>
                    <label>Frequency<select value={resourceForm.period} onChange={(event) => setResourceForm({ ...resourceForm, period: event.target.value })}><option>monthly</option><option>weekly</option><option>yearly</option></select></label>
                  </div>
                )}
                <button className="primary-button">{editingResource ? 'Save changes' : `Create ${resourceModal}`} <span>↗</span></button>
              </form>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {commandOpen && (
          <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setCommandOpen(false)}>
            <motion.div className="command-modal" initial={{ y: 18, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 18, opacity: 0 }} onClick={(event) => event.stopPropagation()}>
              <input autoFocus value={commandQuery} onChange={(event) => setCommandQuery(event.target.value)} placeholder="Jump to a view or transaction" />
              <div className="command-group">
                {commandResults.navigation.map((item) => (
                  <button key={item.id} onClick={() => { setActiveView(item.id); setCommandOpen(false) }}>{item.icon} {item.label}</button>
                ))}
              </div>
              {commandResults.matches.length > 0 && (
                <div className="command-group">
                  {commandResults.matches.map((item) => (
                    <button key={item.id} onClick={() => { editTransaction(item); setCommandOpen(false) }}>{item.title} · {money(item.amount)}</button>
                  ))}
                </div>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence>
        {confirm && (
          <ConfirmDialog
            title={confirm.title}
            copy={confirm.copy}
            confirmLabel={confirm.confirmLabel}
            onCancel={() => setConfirm(null)}
            onConfirm={async () => {
              const action = confirm.run
              setConfirm(null)
              try {
                await action()
              } catch {
                setError('That action could not be completed.')
              }
            }}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>{toast && <motion.div className="toast" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 20 }}>{toast}</motion.div>}</AnimatePresence>
    </div>
  )
}

function ResourceView({ kicker, title, copy, items, empty, type, onAdd, onEdit, onDelete }) {
  return (
    <motion.div className="view" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
      <PageIntro kicker={kicker} title={title} copy={copy} action={<button className="primary-button compact" onClick={onAdd}>+ Add {type}</button>} />
      <div className="resource-grid">
        {items.length ? items.map((item) => (
          <motion.div className="resource-card panel" key={item.id} whileHover={{ y: -4 }}>
            <span className="resource-icon">{type === 'investment' ? '◈' : '▣'}</span>
            <span className="section-kicker">{(item.account_type || item.kind || type).toUpperCase()}</span>
            <h2>{item.name || item.title}</h2>
            <strong>{money(item.amount || item.target_amount || item.opening_balance)}</strong>
            <p>{item.institution || item.category || item.merchant || item.due_date || 'Local finance record'}</p>
            <div className="card-actions">
              <button onClick={() => onEdit(type, item)}>Edit</button>
              <button onClick={() => onDelete(type, item)}>Delete</button>
            </div>
          </motion.div>
        )) : (
          <div className="panel empty-resource">
            <span className="empty-orbit">+</span>
            <h3>{empty}</h3>
            <button className="ghost-button" onClick={onAdd}>Create {type} <span>↗</span></button>
          </div>
        )}
      </div>
    </motion.div>
  )
}
