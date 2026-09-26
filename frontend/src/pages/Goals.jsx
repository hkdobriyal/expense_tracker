import { useQuery } from '@tanstack/react-query'
import { Goal, Minus, Pencil, PiggyBank, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { CashFlowChart } from '../components/charts'
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Field, FormError, Loading, Modal, Money, PageHead, Progress, Select, Stat } from '../components/ui'
import { api } from '../lib/api'
import { longDate, money, pct, toInput, todayISO } from '../lib/format'
import { useAccounts, useLedgerMutation, useSession, useToast } from '../lib/hooks'
import { useNewParam } from './Accounts'

const TYPES = [['emergency_fund', 'Emergency fund'], ['vacation', 'Vacation'], ['house', 'House'], ['car', 'Car'], ['education', 'Education'], ['investment', 'Investment'], ['debt_payoff', 'Debt payoff'], ['wedding', 'Wedding'], ['custom', 'Custom']]
const LABEL = Object.fromEntries(TYPES)

export default function Goals() {
  const session = useSession()
  const toast = useToast()
  const cur = session.settings.base_currency
  const goals = useQuery({ queryKey: ['goals'], queryFn: () => api.get('/goals') })
  const savings = useQuery({ queryKey: ['analytics-series', 'savings'], queryFn: () => api.get('/analytics/series', { granularity: 'month', preset: '1y' }) })
  const summary = useQuery({ queryKey: ['analytics-summary', 'this_month'], queryFn: () => api.get('/analytics/summary', { preset: 'this_month' }) })
  const { data: accounts = [] } = useAccounts()
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [contrib, setContrib] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const openNew = () => { setError(null); setEditing('new'); setForm({ name: '', goal_type: 'emergency_fund', target: '', target_date: '', linked_account_id: '', initial_amount: '' }) }
  useNewParam(openNew)
  const openEdit = (g) => { setError(null); setEditing(g); setForm({ name: g.name, goal_type: g.goal_type, target: toInput(g.target_minor, g.currency), target_date: g.target_date || '', linked_account_id: g.linked_account_id ? String(g.linked_account_id) : '', status: g.status }) }
  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/goals', b) : api.put(`/goals/${editing.id}`, b)), { onSuccess: () => { toast.success('Goal saved'); setEditing(null) }, onError: setError })
  const addContribution = useLedgerMutation(({ goal, amount, date, note }) => api.post(`/goals/${goal.id}/contributions`, { amount, date, note }), {
    onSuccess: (r) => { toast.success(r.goal.is_complete ? `🎉 ${r.goal.name} is fully funded!` : 'Saved'); setContrib(null) },
    onError: setError,
  })
  const remove = useLedgerMutation((id) => api.delete(`/goals/${id}`), { onSuccess: () => { toast.success('Goal deleted'); setDeleting(null) } })

  const list = goals.data || []
  const t = summary.data?.totals
  const series = (savings.data?.series || []).map((p) => ({ ...p, savings: p.savings }))

  return (
    <>
      <PageHead kicker="Plan" title="Goals & savings" actions={<Button variant="primary" icon={Plus} onClick={openNew}>New goal</Button>}>
        Track progress toward targets. Link a goal to an account (e.g. an FD) and its balance becomes the progress.
      </PageHead>
      <div className="grid grid-4" style={{ marginBottom: 16 }}>
        <Stat label="Saved this month" icon={PiggyBank} value={t ? t.savings : '—'} currency={cur} meta="income − expenses" />
        <Stat label="Savings rate" value={t ? pct(t.savings_rate) : '—'} meta="this month" />
        <Stat label="Invested this month" value={t ? t.invested : '—'} currency={cur} meta="SIPs, stocks, deposits" />
        <Stat label="Toward goals" value={list.reduce((s, g) => s + (g.currency === cur ? g.current : 0), 0)} currency={cur} meta={`${list.filter((g) => g.status === 'active').length} active goals`} />
      </div>
      {series.some((p) => p.savings) && <Card title="Monthly savings" sub="Last 12 months" style={{ marginBottom: 16 }}><CashFlowChart data={series} currency={cur} dataKey="savings" name="Saved" height={200} /></Card>}
      <ErrorNote error={goals.error} onRetry={goals.refetch} />
      {goals.isLoading ? <Loading /> : !list.length ? (
        <Card><Empty icon={Goal} title="No goals yet" action={<Button variant="primary" icon={Plus} onClick={openNew}>Create a goal</Button>}>An emergency fund of 6 months' expenses is a good first goal.</Empty></Card>
      ) : (
        <div className="cards">
          {list.map((g) => (
            <Card key={g.id} hover>
              <div className="row between">
                <Badge tone={g.status === 'completed' ? 'success' : g.behind_by_pct > 10 ? 'warning' : 'accent'}>{g.status === 'completed' ? 'Completed' : LABEL[g.goal_type]}</Badge>
                <div className="row" style={{ gap: 2 }}>
                  <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${g.name}`} onClick={() => openEdit(g)} />
                  <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Delete ${g.name}`} onClick={() => setDeleting(g)} />
                </div>
              </div>
              <h3 style={{ margin: '12px 0 4px' }}>{g.name}</h3>
              <div className="row between" style={{ alignItems: 'baseline' }}><Money minor={g.current} currency={g.currency} animated className="" /><span className="faint num" style={{ fontSize: 13 }}>of {money(g.target_minor, g.currency)}</span></div>
              <div style={{ margin: '10px 0' }}><Progress value={g.progress_pct} tone={g.is_complete ? 'success' : ''} label={`${g.name} progress`} /></div>
              <div className="stack" style={{ gap: 4, fontSize: 13 }}>
                <span className="muted">{pct(g.progress_pct)} · {money(g.remaining, g.currency)} to go</span>
                {g.target_date && <span className="faint">Target {longDate(g.target_date)}{g.days_left != null && g.days_left >= 0 ? ` · ${g.days_left} days` : ''}</span>}
                {g.monthly_needed > 0 && <span className="faint">Save {money(g.monthly_needed, g.currency)}/month to make it</span>}
                {g.behind_by_pct > 0 && <span className="expense">Behind schedule by {g.behind_by_pct} pts</span>}
                {g.linked_account_id && <span className="faint">Tracks {accounts.find((a) => a.id === g.linked_account_id)?.name || 'linked account'}</span>}
              </div>
              {!g.linked_account_id && g.status !== 'archived' && (
                <div className="row" style={{ marginTop: 14 }}>
                  <Button size="sm" icon={Plus} onClick={() => { setError(null); setContrib({ goal: g, amount: '', date: todayISO(), note: '', sign: 1 }) }}>Add money</Button>
                  <Button size="sm" variant="ghost" icon={Minus} onClick={() => { setError(null); setContrib({ goal: g, amount: '', date: todayISO(), note: '', sign: -1 }) }}>Withdraw</Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'New goal' : 'Edit goal'}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate({ name: form.name, goal_type: form.goal_type, target: form.target, target_date: form.target_date || null, linked_account_id: form.linked_account_id ? Number(form.linked_account_id) : null, initial_amount: editing === 'new' && form.initial_amount ? form.initial_amount : null, status: form.status || 'active' }) }}>
          <div className="form-grid">
            <Field label="Name" required className="full"><input className="input" required value={form.name || ''} placeholder="e.g. Goa trip" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Type"><Select value={form.goal_type} onChange={(e) => setForm({ ...form, goal_type: e.target.value })} options={TYPES.map(([value, label]) => ({ value, label }))} /></Field>
            <Field label={`Target (${cur})`} required><input className="input" required inputMode="decimal" value={form.target || ''} onChange={(e) => setForm({ ...form, target: e.target.value })} /></Field>
            <Field label="Target date"><input className="input" type="date" value={form.target_date} onChange={(e) => setForm({ ...form, target_date: e.target.value })} /></Field>
            <Field label="Track an account instead" hint="Progress = that account's balance"><Select value={form.linked_account_id} onChange={(e) => setForm({ ...form, linked_account_id: e.target.value })} placeholder="No – I'll add contributions" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
            {editing === 'new' && !form.linked_account_id && <Field label="Already saved"><input className="input" inputMode="decimal" value={form.initial_amount} onChange={(e) => setForm({ ...form, initial_amount: e.target.value })} /></Field>}
            {editing !== 'new' && <Field label="Status"><Select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} options={[{ value: 'active', label: 'Active' }, { value: 'completed', label: 'Completed' }, { value: 'archived', label: 'Archived' }]} /></Field>}
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save goal</Button></div>
        </form>
      </Modal>
      <Modal open={!!contrib} onClose={() => setContrib(null)} title={contrib?.sign > 0 ? `Add to ${contrib?.goal.name}` : `Withdraw from ${contrib?.goal.name}`}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); addContribution.mutate({ goal: contrib.goal, amount: contrib.sign > 0 ? contrib.amount : `-${contrib.amount}`, date: contrib.date, note: contrib.note }) }}>
          <div className="form-grid">
            <Field label="Amount" required><input className="input amount" required autoFocus inputMode="decimal" value={contrib?.amount || ''} onChange={(e) => setContrib({ ...contrib, amount: e.target.value.replace(/[^0-9.]/g, '') })} /></Field>
            <Field label="Date"><input className="input" type="date" value={contrib?.date || ''} onChange={(e) => setContrib({ ...contrib, date: e.target.value })} /></Field>
            <Field label="Note" className="full"><input className="input" value={contrib?.note || ''} onChange={(e) => setContrib({ ...contrib, note: e.target.value })} /></Field>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setContrib(null)}>Cancel</Button><Button type="submit" variant="primary" loading={addContribution.isPending}>Save</Button></div>
        </form>
      </Modal>
      <Confirm open={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name}?`} message="The goal and its contribution history are removed. Accounts and transactions are not affected." loading={remove.isPending} onConfirm={() => remove.mutate(deleting.id)} />
    </>
  )
}
