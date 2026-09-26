import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeftRight, BarChart3, Bell, CalendarClock, CheckCheck, CreditCard, FileSpreadsheet, FlaskConical, Gauge, Goal, Landmark, LayoutDashboard,
  LogOut, Menu, PiggyBank, Plus, Repeat, Search, Settings, Shapes, Sparkles, TrendingUp, Upload, Wallet, Waves,
} from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { money, relativeTime } from '../lib/format'
import { useSession } from '../lib/hooks'
import TransactionForm from './TransactionForm'
import { Badge, Button, Drawer, Empty } from './ui'

export const NAV = [
  { section: 'Overview', items: [{ to: '/', label: 'Dashboard', icon: LayoutDashboard }] },
  { section: 'Money', items: [
    { to: '/transactions', label: 'Transactions', icon: ArrowLeftRight },
    { to: '/accounts', label: 'Accounts', icon: Wallet },
    { to: '/categories', label: 'Categories & rules', icon: Shapes },
  ] },
  { section: 'Plan', items: [
    { to: '/budgets', label: 'Budgets', icon: Gauge },
    { to: '/goals', label: 'Goals & savings', icon: Goal },
    { to: '/bills', label: 'Bills', icon: CalendarClock },
    { to: '/subscriptions', label: 'Subscriptions', icon: CreditCard },
    { to: '/recurring', label: 'Recurring', icon: Repeat },
  ] },
  { section: 'Insights', items: [
    { to: '/analytics', label: 'Analytics', icon: BarChart3 },
    { to: '/cash-flow', label: 'Cash flow', icon: Waves },
    { to: '/net-worth', label: 'Net worth', icon: TrendingUp },
    { to: '/reports', label: 'Reports', icon: FileSpreadsheet },
  ] },
  { section: 'Connect', items: [
    { to: '/banks', label: 'Bank connections', icon: Landmark },
    { to: '/import', label: 'Import statement', icon: Upload },
  ] },
  { section: 'Automation', items: [
    { to: '/alerts', label: 'Alerts', icon: Sparkles },
    { to: '/settings', label: 'Settings', icon: Settings },
  ] },
]
const ALL = NAV.flatMap((s) => s.items)

const ActionsContext = createContext({ addTransaction: () => {}, editTransaction: () => {}, openPalette: () => {} })
export const useActions = () => useContext(ActionsContext)

export default function Layout() {
  const session = useSession()
  const location = useLocation()
  const navigate = useNavigate()
  const [txnModal, setTxnModal] = useState({ open: false, transaction: null, type: 'expense' })
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [inboxOpen, setInboxOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const unread = useQuery({ queryKey: ['unread'], queryFn: () => api.get('/notifications/unread-count'), refetchInterval: 60_000 })

  const actions = useMemo(() => ({
    addTransaction: (type = 'expense') => setTxnModal({ open: true, transaction: null, type }),
    editTransaction: (transaction) => setTxnModal({ open: true, transaction, type: transaction.type }),
    openPalette: () => setPaletteOpen(true),
  }), [])

  useEffect(() => {
    const onKey = (e) => {
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName) || e.target.isContentEditable
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPaletteOpen((o) => !o) }
      else if (!typing && !e.metaKey && !e.ctrlKey && e.key.toLowerCase() === 'n' && !txnModal.open) { e.preventDefault(); actions.addTransaction() }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [actions, txnModal.open])
  useEffect(() => setMenuOpen(false), [location.pathname])

  const current = ALL.find((i) => (i.to === '/' ? location.pathname === '/' : location.pathname.startsWith(i.to)))

  return (
    <ActionsContext.Provider value={actions}>
      <div className={session.settings.reduce_motion ? 'reduce-motion' : ''}>
        {session.user.is_demo && (
          <div className="demo-banner" role="status">
            <FlaskConical size={16} /> DEMO WORKSPACE – sample data from a sandbox bank, not your real accounts.
            <Button size="sm" onClick={session.logout}>Exit demo</Button>
          </div>
        )}
        <div className="shell">
          <aside className="sidebar" aria-label="Main navigation">
            <div className="brand"><span className="brand-mark"><PiggyBank size={18} /></span>ledgerly</div>
            <SidebarNav unread={unread.data?.unread} />
            <div style={{ marginTop: 'auto', paddingTop: 16 }}>
              <button type="button" className="nav-link" style={{ width: '100%', border: 0, background: 'none', cursor: 'pointer' }} onClick={() => setPaletteOpen(true)}>
                <Search size={17} />Search <span className="kbd" style={{ marginLeft: 'auto' }}>Ctrl K</span>
              </button>
              <div className="row" style={{ padding: '12px 10px 0' }}>
                <span className="avatar" aria-hidden>{(session.user.display_name || session.user.email)[0].toUpperCase()}</span>
                <div className="grow"><div className="truncate" style={{ fontWeight: 700, fontSize: 14 }}>{session.user.display_name}</div><div className="faint truncate" style={{ fontSize: 12 }}>{session.user.email}</div></div>
                <Button variant="ghost" icon={LogOut} aria-label="Sign out" onClick={session.logout} />
              </div>
            </div>
          </aside>
          <div className="main">
            <header className="topbar">
              <Button variant="ghost" icon={Menu} className="show-mobile" aria-label="Menu" onClick={() => setMenuOpen(true)} />
              <h1 className="grow truncate">{current?.label || 'Ledgerly'}</h1>
              <Button variant="ghost" icon={Search} aria-label="Search (Ctrl K)" onClick={() => setPaletteOpen(true)} />
              <Button variant="ghost" icon={Bell} aria-label={`Notifications${unread.data?.unread ? `, ${unread.data.unread} unread` : ''}`} onClick={() => setInboxOpen(true)} style={{ position: 'relative' }}>
                {unread.data?.unread ? <span className="chip-count" style={{ position: 'absolute', top: 2, right: 0 }}>{unread.data.unread > 9 ? '9+' : unread.data.unread}</span> : null}
              </Button>
              <Button variant="primary" icon={Plus} onClick={() => actions.addTransaction()} className="hide-mobile">Add <span className="kbd" style={{ color: 'inherit', borderColor: 'currentColor', opacity: 0.6 }}>N</span></Button>
            </header>
            <main className="content" id="main"><Outlet /></main>
          </div>
        </div>
        <nav className="mobile-nav" aria-label="Quick navigation">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : '')}><LayoutDashboard size={19} />Home</NavLink>
          <NavLink to="/transactions" className={({ isActive }) => (isActive ? 'active' : '')}><ArrowLeftRight size={19} />Ledger</NavLink>
          <button type="button" className="add" onClick={() => actions.addTransaction()} aria-label="Add transaction"><Plus size={20} />Add</button>
          <NavLink to="/budgets" className={({ isActive }) => (isActive ? 'active' : '')}><Gauge size={19} />Budgets</NavLink>
          <button type="button" onClick={() => setMenuOpen(true)}><Menu size={19} />More</button>
        </nav>
        <Drawer open={menuOpen} onClose={() => setMenuOpen(false)} title="Menu"><SidebarNav unread={unread.data?.unread} /></Drawer>
        <TransactionForm open={txnModal.open} transaction={txnModal.transaction} initialType={txnModal.type} onClose={() => setTxnModal((m) => ({ ...m, open: false }))} />
        <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} onAction={(fn) => { setPaletteOpen(false); fn({ navigate, actions }) }} />
        <Inbox open={inboxOpen} onClose={() => setInboxOpen(false)} />
      </div>
    </ActionsContext.Provider>
  )
}

function SidebarNav({ unread }) {
  return NAV.map((section) => (
    <div key={section.section}>
      <div className="nav-section">{section.section}</div>
      {section.items.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
          <Icon size={17} aria-hidden />{label}
          {to === '/alerts' && unread ? <span className="badge critical">{unread}</span> : null}
        </NavLink>
      ))}
    </div>
  ))
}

const COMMANDS = [
  { label: 'Add expense', icon: Plus, run: ({ actions }) => actions.addTransaction('expense') },
  { label: 'Add income', icon: Plus, run: ({ actions }) => actions.addTransaction('income') },
  { label: 'Add transfer', icon: ArrowLeftRight, run: ({ actions }) => actions.addTransaction('transfer') },
  { label: 'Create budget', icon: Gauge, run: ({ navigate }) => navigate('/budgets?new=1') },
  { label: 'Create goal', icon: Goal, run: ({ navigate }) => navigate('/goals?new=1') },
  { label: 'Sync bank', icon: Landmark, run: ({ navigate }) => navigate('/banks') },
  { label: 'Import statement', icon: Upload, run: ({ navigate }) => navigate('/import') },
  { label: 'Create alert', icon: Sparkles, run: ({ navigate }) => navigate('/alerts?new=1') },
  { label: 'Review transactions', icon: CheckCheck, run: ({ navigate }) => navigate('/transactions?reviewed=false') },
]

function CommandPalette({ open, onClose, onAction }) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const { editTransaction } = useActions()
  const [debounced, setDebounced] = useState('')
  useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 180); return () => clearTimeout(t) }, [q])
  useEffect(() => { if (open) { setQ(''); setActive(0); setTimeout(() => inputRef.current?.focus(), 20) } }, [open])
  const search = useQuery({ queryKey: ['search', debounced], queryFn: () => api.get('/search', { q: debounced }), enabled: open && debounced.length > 1 })

  const items = useMemo(() => {
    const lower = q.toLowerCase()
    const out = []
    COMMANDS.filter((c) => c.label.toLowerCase().includes(lower)).forEach((c) => out.push({ group: 'Actions', ...c }))
    ALL.filter((n) => n.label.toLowerCase().includes(lower)).forEach((n) => out.push({ group: 'Go to', label: n.label, icon: n.icon, run: ({ navigate }) => navigate(n.to) }))
    const r = search.data
    if (r && debounced.length > 1) {
      r.transactions.forEach((t) => out.push({ group: 'Transactions', label: `${t.description} · ${money(t.amount_minor, t.currency)} · ${t.date}`, icon: ArrowLeftRight, run: async () => editTransaction(await api.get(`/transactions/${t.id}`)) }))
      r.merchants.forEach((m) => out.push({ group: 'Merchants', label: m.name, icon: Shapes, run: ({ navigate }) => navigate(`/transactions?merchant_id=${m.id}`) }))
      r.accounts.forEach((a) => out.push({ group: 'Accounts', label: a.name, icon: Wallet, run: ({ navigate }) => navigate(`/transactions?account_id=${a.id}`) }))
      r.categories.forEach((c) => out.push({ group: 'Categories', label: c.name, icon: Shapes, run: ({ navigate }) => navigate(`/transactions?category_id=${c.id}`) }))
      r.bills.forEach((b) => out.push({ group: 'Bills', label: b.name, icon: CalendarClock, run: ({ navigate }) => navigate('/bills') }))
      r.subscriptions.forEach((s) => out.push({ group: 'Subscriptions', label: s.name, icon: CreditCard, run: ({ navigate }) => navigate('/subscriptions') }))
      r.tags.forEach((t) => out.push({ group: 'Tags', label: `#${t.name}`, icon: Shapes, run: ({ navigate }) => navigate(`/transactions?tag=${encodeURIComponent(t.name)}`) }))
    }
    return out
  }, [q, search.data, debounced, editTransaction])

  if (!open) return null
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    if (e.key === 'Enter' && items[active]) onAction(items[active].run)
    if (e.key === 'Escape') onClose()
  }
  let lastGroup = null
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input ref={inputRef} value={q} onChange={(e) => { setQ(e.target.value); setActive(0) }} onKeyDown={onKey} placeholder="Search transactions, merchants, pages… or type a command" aria-label="Search" role="combobox" aria-expanded="true" aria-controls="palette-list" />
        <div className="palette-list" id="palette-list" role="listbox">
          {items.length === 0 && <div className="empty" style={{ padding: 24 }}>{search.isFetching ? 'Searching…' : 'No matches'}</div>}
          {items.map((item, i) => {
            const header = item.group !== lastGroup ? <div className="palette-group" key={`g-${item.group}`}>{item.group}</div> : null
            lastGroup = item.group
            const Icon = item.icon
            return [header, (
              <button type="button" key={`${item.group}-${item.label}-${i}`} role="option" aria-selected={i === active} className="palette-item" onMouseEnter={() => setActive(i)} onClick={() => onAction(item.run)}>
                <Icon size={16} className="faint" />{item.label}
              </button>
            )]
          })}
        </div>
      </div>
    </div>
  )
}

function Inbox({ open, onClose }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const inbox = useQuery({ queryKey: ['notifications'], queryFn: () => api.get('/notifications', { limit: 60 }), enabled: open })
  const refresh = useCallback(() => { qc.invalidateQueries({ queryKey: ['notifications'] }); qc.invalidateQueries({ queryKey: ['unread'] }) }, [qc])
  const markAll = async () => { await api.post('/notifications/read-all'); refresh() }
  const openItem = async (n) => {
    if (!n.read) { await api.post(`/notifications/${n.id}/read`); refresh() }
    if (n.link) { navigate(n.link); onClose() }
  }
  const tone = { critical: 'critical', warning: 'warning', success: 'success', info: 'accent' }
  return (
    <Drawer open={open} onClose={onClose} title="Notifications" actions={<Button size="sm" variant="ghost" icon={CheckCheck} onClick={markAll}>Mark all read</Button>}>
      {inbox.data?.items?.length === 0 && <Empty icon={Bell} title="All quiet">Alerts you configure (budgets, bills, large payments…) appear here.</Empty>}
      <div className="list">
        {inbox.data?.items?.map((n) => (
          <div key={n.id} className="list-row clickable" onClick={() => openItem(n)} role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && openItem(n)} style={{ alignItems: 'flex-start', opacity: n.read ? 0.62 : 1 }}>
            <span className="dot" style={{ marginTop: 7, background: n.read ? 'transparent' : 'var(--accent)' }} />
            <div className="grow">
              <div className="row between"><strong style={{ fontSize: 14 }}>{n.title}</strong><Badge tone={tone[n.severity]}>{n.category}</Badge></div>
              <div className="muted" style={{ fontSize: 13, marginTop: 3 }}>{n.message}</div>
              <div className="faint" style={{ fontSize: 12, marginTop: 4 }}>{relativeTime(n.created_at)}</div>
            </div>
          </div>
        ))}
      </div>
      <Button variant="ghost" size="sm" style={{ marginTop: 12 }} onClick={() => { navigate('/alerts?tab=history'); onClose() }}>Alert history & delivery status →</Button>
    </Drawer>
  )
}
