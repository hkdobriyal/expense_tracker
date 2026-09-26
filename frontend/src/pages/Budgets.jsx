import { useQuery } from '@tanstack/react-query'
import { Gauge, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Field, FormError, Loading, Modal, Money, PageHead, Progress, Select } from '../components/ui'
import { api } from '../lib/api'
import { money, monthLabel, shortDate, toInput } from '../lib/format'
import { useCategories, useLedgerMutation, useSession, useToast } from '../lib/hooks'
import { useNewParam } from './Accounts'

const PERIODS = [{ value: 'monthly', label: 'Monthly' }, { value: 'weekly', label: 'Weekly' }, { value: 'yearly', label: 'Yearly' }, { value: 'custom', label: 'Custom dates' }]
const THRESHOLDS = [50, 70, 80, 90, 100]

export default function Budgets() {
  const session = useSession()
  const toast = useToast()
  const cur = session.settings.base_currency
  const { data: categories = [] } = useCategories()
  const budgets = useQuery({ queryKey: ['budgets'], queryFn: () => api.get('/budgets') })
  const perf = useQuery({ queryKey: ['budget-performance'], queryFn: () => api.get('/analytics/budgets', { months: 6 }) })
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const openNew = () => { setError(null); setEditing('new'); setForm({ name: '', category_id: '', period: 'monthly', amount: '', start_date: '', end_date: '', include_subcategories: true, alerts: [80, 100] }) }
  useNewParam(openNew)
  const openEdit = (b) => { setError(null); setEditing(b); setForm({ name: b.name, category_id: b.category_id ? String(b.category_id) : '', period: b.period, amount: toInput(b.amount_minor, cur), start_date: b.start_date || '', end_date: b.end_date || '', include_subcategories: b.include_subcategories, alerts: [] }) }
  const save = useLedgerMutation((body) => (editing === 'new' ? api.post('/budgets', body) : api.put(`/budgets/${editing.id}`, body)), { onSuccess: () => { toast.success('Budget saved'); setEditing(null) }, onError: setError })
  const remove = useLedgerMutation((id) => api.delete(`/budgets/${id}`), { onSuccess: () => { toast.success('Budget deleted'); setDeleting(null) } })

  const submit = (e) => {
    e.preventDefault()
    const body = { name: form.name, category_id: form.category_id ? Number(form.category_id) : null, period: form.period, amount: form.amount, start_date: form.start_date || null, end_date: form.end_date || null, include_subcategories: form.include_subcategories }
    if (editing === 'new') body.alert_thresholds = form.alerts
    save.mutate(body)
  }
  const list = budgets.data || []
  const totals = list.filter((b) => b.period === 'monthly' && b.category_id).reduce((s, b) => ({ limit: s.limit + b.limit, spent: s.spent + b.spent }), { limit: 0, spent: 0 })
  const perfData = (perf.data?.months || []).map((m) => ({ month: m.month, ...Object.fromEntries(m.budgets.map((b) => [b.name, b.usage_pct])) }))
  const perfNames = perf.data?.months?.[0]?.budgets?.map((b) => b.name) || []
  const colors = ['#8ae6ff', '#b29bff', '#7ef0c2', '#ffd8a8', '#ff8fab', '#70d6ff']

  return (
    <>
      <PageHead kicker="Plan" title="Budgets" actions={<Button variant="primary" icon={Plus} onClick={openNew}>New budget</Button>}>
        Limits per category and period. Spending in subcategories counts toward the parent, and refunds reduce it.
      </PageHead>
      <ErrorNote error={budgets.error} onRetry={budgets.refetch} />
      {budgets.isLoading ? <Loading /> : !list.length ? (
        <Card><Empty icon={Gauge} title="No budgets yet" action={<Button variant="primary" icon={Plus} onClick={openNew}>Create your first budget</Button>}>For example Food ₹12,000 per month, with alerts at 80% and 100%.</Empty></Card>
      ) : (
        <>
          {totals.limit > 0 && (
            <Card style={{ marginBottom: 16 }}>
              <div className="row between wrap"><div><div className="faint" style={{ fontSize: 13 }}>Monthly category budgets</div><div className="num" style={{ fontSize: 24, fontWeight: 700 }}>{money(totals.spent, cur)} <span className="faint" style={{ fontSize: 16 }}>of {money(totals.limit, cur)}</span></div></div><Badge tone={totals.spent > totals.limit ? 'critical' : 'accent'}>{money(totals.limit - totals.spent, cur)} left</Badge></div>
              <div style={{ marginTop: 12 }}><Progress value={(totals.spent / totals.limit) * 100} tone={totals.spent > totals.limit ? 'over' : ''} label="Total budget used" /></div>
            </Card>
          )}
          <div className="cards">
            {list.map((b) => (
              <Card key={b.id} hover>
                <div className="row between">
                  <div className="row"><span className="dot" style={{ background: b.category_color || 'var(--accent)' }} /><strong>{b.name}</strong></div>
                  <div className="row" style={{ gap: 2 }}>
                    <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${b.name}`} onClick={() => openEdit(b)} />
                    <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Delete ${b.name}`} onClick={() => setDeleting(b)} />
                  </div>
                </div>
                <div className="faint" style={{ fontSize: 12, margin: '4px 0 12px' }}>{b.category} · {b.period} · {shortDate(b.window_start)}–{shortDate(b.window_end)}</div>
                <div className="row between" style={{ alignItems: 'baseline' }}>
                  <Money minor={b.spent} currency={cur} className={b.status === 'over' ? 'expense' : ''} animated />
                  <span className="faint num" style={{ fontSize: 13 }}>of {money(b.limit, cur)}</span>
                </div>
                <div style={{ margin: '10px 0' }}><Progress value={b.usage_pct} tone={b.status === 'over' ? 'over' : b.status === 'warning' ? 'warning' : ''} label={`${b.name} used`} /></div>
                <div className="row between" style={{ fontSize: 13 }}>
                  <span className={b.remaining < 0 ? 'expense' : 'muted'}>{b.remaining < 0 ? `${money(-b.remaining, cur)} over` : `${money(b.remaining, cur)} left`}</span>
                  <span className="faint">{b.usage_pct}% · {b.days_left}d left</span>
                </div>
                {b.ahead_of_pace && b.status !== 'over' && <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>Ahead of an even pace ({money(b.expected_spend_to_date, cur)} by today)</div>}
                {b.category_id && <Link className="faint" style={{ fontSize: 12, display: 'inline-block', marginTop: 10 }} to={`/transactions?category_id=${b.category_id}&start=${b.window_start}&end=${b.window_end}`}>See transactions →</Link>}
              </Card>
            ))}
          </div>
          {perfData.length > 0 && perfNames.length > 0 && (
            <Card title="Budget performance" sub="% of monthly limit used, last 6 months" style={{ marginTop: 16 }}>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={perfData}>
                  <CartesianGrid vertical={false} stroke="var(--border)" />
                  <XAxis dataKey="month" tickFormatter={monthLabel} stroke="var(--text-3)" fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis unit="%" stroke="var(--text-3)" fontSize={11} tickLine={false} axisLine={false} width={44} />
                  <Tooltip formatter={(v) => `${v}%`} labelFormatter={monthLabel} contentStyle={{ background: 'var(--surface-solid)', border: '1px solid var(--border-strong)', borderRadius: 12 }} />
                  {perfNames.map((n, i) => <Bar key={n} dataKey={n} fill={colors[i % colors.length]} radius={[4, 4, 0, 0]} maxBarSize={18} />)}
                </BarChart>
              </ResponsiveContainer>
            </Card>
          )}
        </>
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'New budget' : 'Edit budget'}>
        <form className="stack" onSubmit={submit}>
          <div className="form-grid">
            <Field label="Name" required className="full"><input className="input" required value={form.name || ''} placeholder="e.g. Food" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Category" hint="Empty = all spending"><Select value={form.category_id} onChange={(e) => { const c = categories.find((x) => String(x.id) === e.target.value); setForm({ ...form, category_id: e.target.value, name: form.name || c?.name || '' }) }} placeholder="All spending" options={categoryOptions(categories, 'expense')} /></Field>
            <Field label={`Limit (${cur})`} required><input className="input" required inputMode="decimal" value={form.amount || ''} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
            <Field label="Period"><Select value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })} options={PERIODS} /></Field>
            {form.period === 'custom' && <>
              <Field label="From" required><input className="input" type="date" required value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></Field>
              <Field label="To" required><input className="input" type="date" required value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
            </>}
            <label className="checkbox full"><input type="checkbox" checked={form.include_subcategories} onChange={(e) => setForm({ ...form, include_subcategories: e.target.checked })} />Include subcategories</label>
            {editing === 'new' && (
              <div className="full">
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Alert me at</div>
                <div className="row wrap">{THRESHOLDS.map((t) => (
                  <label key={t} className="checkbox"><input type="checkbox" checked={form.alerts?.includes(t)} onChange={(e) => setForm({ ...form, alerts: e.target.checked ? [...form.alerts, t] : form.alerts.filter((x) => x !== t) })} />{t}%</label>
                ))}</div>
                <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>Each threshold alerts once per period. Channels follow Settings → Notifications.</div>
              </div>
            )}
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save budget</Button></div>
        </form>
      </Modal>
      <Confirm open={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name}?`} message="Its alert rules are removed as well. Transactions are not affected." loading={remove.isPending} onConfirm={() => remove.mutate(deleting.id)} />
    </>
  )
}
