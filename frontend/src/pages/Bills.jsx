import { useQuery } from '@tanstack/react-query'
import { CalendarClock, Check, Pencil, Plus, SkipForward, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Field, FormError, Loading, Modal, Money, PageHead, Select } from '../components/ui'
import { api } from '../lib/api'
import { FREQ_LABEL, daysUntil, longDate, toInput, todayISO } from '../lib/format'
import { useAccounts, useCategories, useLedgerMutation, useSession, useToast } from '../lib/hooks'
import { useNewParam } from './Accounts'

const STATUS = { overdue: ['Overdue', 'critical'], due_today: ['Due today', 'warning'], due_soon: ['Due soon', 'warning'], upcoming: ['Upcoming', 'accent'], paid: ['Paid', 'success'], skipped: ['Skipped', ''] }
const FREQS = Object.entries(FREQ_LABEL).map(([value, label]) => ({ value, label }))

export default function Bills() {
  const session = useSession()
  const toast = useToast()
  const cur = session.settings.base_currency
  const { data: accounts = [] } = useAccounts()
  const { data: categories = [] } = useCategories()
  const [showPast, setShowPast] = useState(false)
  const bills = useQuery({ queryKey: ['bills', showPast], queryFn: () => api.get('/bills', { include_inactive: showPast }) })
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [paying, setPaying] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const openNew = () => { setError(null); setEditing('new'); setForm({ name: '', provider: '', amount: '', frequency: 'monthly', next_due_date: todayISO(), autopay: false, account_id: session.settings.default_account_id ? String(session.settings.default_account_id) : '', category_id: '', notes: '' }) }
  useNewParam(openNew)
  const openEdit = (b) => { setError(null); setEditing(b); setForm({ name: b.name, provider: b.provider, amount: toInput(b.amount_minor, b.currency), frequency: b.frequency, next_due_date: b.next_due_date, autopay: b.autopay, account_id: b.account_id ? String(b.account_id) : '', category_id: b.category_id ? String(b.category_id) : '', notes: b.notes }) }
  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/bills', b) : api.put(`/bills/${editing.id}`, b)), { onSuccess: () => { toast.success('Bill saved'); setEditing(null) }, onError: setError })
  const pay = useLedgerMutation(({ bill, ...body }) => api.post(`/bills/${bill.id}/pay`, body), { onSuccess: () => { toast.success('Marked as paid'); setPaying(null) }, onError: setError })
  const skip = useLedgerMutation((b) => api.post(`/bills/${b.id}/skip`), { onSuccess: () => toast.success('Skipped this cycle') })
  const remove = useLedgerMutation((id) => api.delete(`/bills/${id}`), { onSuccess: () => { toast.success('Bill deleted'); setDeleting(null) } })

  const list = bills.data || []
  const active = list.filter((b) => b.active)
  const monthly = active.filter((b) => b.currency === cur).reduce((s, b) => s + b.monthly_equivalent_minor, 0)
  const dueSoon = active.filter((b) => daysUntil(b.next_due_date) <= 7)

  return (
    <>
      <PageHead kicker="Plan" title="Bills" actions={<><Button onClick={() => setShowPast((v) => !v)}>{showPast ? 'Hide' : 'Show'} paid one-offs</Button><Button variant="primary" icon={Plus} onClick={openNew}>Add bill</Button></>}>
        Rent, utilities, EMIs, insurance. Marking a bill paid records the expense and moves the due date to the next cycle.
      </PageHead>
      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <Card className="stat"><div className="label">Monthly equivalent</div><div className="value"><Money minor={monthly} currency={cur} animated /></div><div className="meta">{active.length} active bills</div></Card>
        <Card className="stat"><div className="label">Due in 7 days</div><div className="value"><Money minor={dueSoon.filter((b) => b.currency === cur).reduce((s, b) => s + b.amount_minor, 0)} currency={cur} /></div><div className="meta">{dueSoon.length} bills</div></Card>
        <Card className="stat"><div className="label">Overdue</div><div className="value">{active.filter((b) => b.status === 'overdue').length}</div><div className="meta">bills past their due date</div></Card>
      </div>
      <ErrorNote error={bills.error} onRetry={bills.refetch} />
      <Card>
        {bills.isLoading ? <Loading /> : !list.length ? <Empty icon={CalendarClock} title="No bills yet" action={<Button variant="primary" icon={Plus} onClick={openNew}>Add a bill</Button>}>You'll get reminders before each due date.</Empty> : (
          <div className="list">
            {list.map((b) => {
              const [label, tone] = STATUS[b.status]
              const days = daysUntil(b.next_due_date)
              return (
                <div key={b.id} className="list-row" style={{ flexWrap: 'wrap' }}>
                  <span className="avatar"><CalendarClock size={16} /></span>
                  <div className="grow" style={{ minWidth: 160 }}>
                    <div style={{ fontWeight: 700 }}>{b.name} {b.autopay && <Badge>auto-pay</Badge>}</div>
                    <div className="faint" style={{ fontSize: 13 }}>{b.provider && `${b.provider} · `}{FREQ_LABEL[b.frequency]} · {b.active ? `due ${longDate(b.next_due_date)}${days >= 0 ? ` (${days === 0 ? 'today' : `in ${days}d`})` : ` (${-days}d ago)`}` : 'closed'}</div>
                  </div>
                  <Badge tone={tone}>{label}</Badge>
                  <Money minor={b.amount_minor} currency={b.currency} />
                  <div className="row" style={{ gap: 2 }}>
                    {b.active && <Button size="sm" icon={Check} onClick={() => { setError(null); setPaying({ bill: b, amount: toInput(b.amount_minor, b.currency), paid_on: todayISO(), account_id: b.account_id ? String(b.account_id) : '', create_transaction: true }) }}>Paid</Button>}
                    {b.active && b.frequency !== 'once' && <Button size="sm" variant="ghost" icon={SkipForward} aria-label="Skip this cycle" onClick={() => skip.mutate(b)} />}
                    <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => openEdit(b)} />
                    <Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete" onClick={() => setDeleting(b)} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'Add bill' : 'Edit bill'}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate({ ...form, account_id: form.account_id ? Number(form.account_id) : null, category_id: form.category_id ? Number(form.category_id) : null }) }}>
          <div className="form-grid">
            <Field label="Name" required><input className="input" required value={form.name || ''} placeholder="e.g. Electricity" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Provider"><input className="input" value={form.provider || ''} placeholder="e.g. BESCOM" onChange={(e) => setForm({ ...form, provider: e.target.value })} /></Field>
            <Field label={`Amount (${cur})`} required><input className="input" required inputMode="decimal" value={form.amount || ''} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
            <Field label="Next due date" required><input className="input" type="date" required value={form.next_due_date || ''} onChange={(e) => setForm({ ...form, next_due_date: e.target.value })} /></Field>
            <Field label="Frequency"><Select value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} options={FREQS} /></Field>
            <Field label="Paid from"><Select value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} placeholder="—" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
            <Field label="Category"><Select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} placeholder="—" options={categoryOptions(categories, 'expense')} /></Field>
            <label className="checkbox"><input type="checkbox" checked={form.autopay} onChange={(e) => setForm({ ...form, autopay: e.target.checked })} />Auto-pay</label>
            <Field label="Notes" className="full"><input className="input" value={form.notes || ''} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save bill</Button></div>
        </form>
      </Modal>
      <Modal open={!!paying} onClose={() => setPaying(null)} title={`Pay ${paying?.bill.name}`}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); pay.mutate({ bill: paying.bill, amount: paying.amount, paid_on: paying.paid_on, account_id: paying.account_id ? Number(paying.account_id) : null, create_transaction: paying.create_transaction }) }}>
          <div className="form-grid">
            <Field label="Amount paid"><input className="input" inputMode="decimal" value={paying?.amount || ''} onChange={(e) => setPaying({ ...paying, amount: e.target.value })} /></Field>
            <Field label="Paid on"><input className="input" type="date" value={paying?.paid_on || ''} onChange={(e) => setPaying({ ...paying, paid_on: e.target.value })} /></Field>
            <Field label="From account" className="full"><Select value={paying?.account_id || ''} onChange={(e) => setPaying({ ...paying, account_id: e.target.value })} placeholder="Choose…" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
            <label className="checkbox full"><input type="checkbox" checked={paying?.create_transaction ?? true} onChange={(e) => setPaying({ ...paying, create_transaction: e.target.checked })} />Record as an expense transaction (untick if it already came in via import or bank sync)</label>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setPaying(null)}>Cancel</Button><Button type="submit" variant="primary" loading={pay.isPending}>Mark paid</Button></div>
        </form>
      </Modal>
      <Confirm open={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name}?`} message="Its payment history is removed too. Recorded transactions stay." loading={remove.isPending} onConfirm={() => remove.mutate(deleting.id)} />
    </>
  )
}
