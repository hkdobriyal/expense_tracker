import { useQuery } from '@tanstack/react-query'
import { Pencil, Plus, Repeat, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Confirm, Empty, Field, FormError, Loading, Modal, Money, PageHead, Select, Switch } from '../components/ui'
import { api } from '../lib/api'
import { FREQ_LABEL, TYPE_LABEL, longDate, toInput, todayISO } from '../lib/format'
import { useAccounts, useCategories, useLedgerMutation, useToast } from '../lib/hooks'

export default function Recurring() {
  const toast = useToast()
  const { data: accounts = [] } = useAccounts()
  const { data: categories = [] } = useCategories()
  const rec = useQuery({ queryKey: ['recurring'], queryFn: () => api.get('/recurring') })
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const open = (r) => {
    setError(null)
    setEditing(r || 'new')
    setForm(r ? { ...r, amount: toInput(r.amount_minor, r.currency), account_id: String(r.account_id), transfer_account_id: r.transfer_account_id ? String(r.transfer_account_id) : '', category_id: r.category_id ? String(r.category_id) : '', end_date: r.end_date || '' }
      : { name: '', type: 'expense', account_id: accounts[0] ? String(accounts[0].id) : '', transfer_account_id: '', amount: '', category_id: '', merchant_name: '', payment_method: '', frequency: 'monthly', next_date: todayISO(), end_date: '', auto_create: true, active: true })
  }
  const body = (f) => ({
    name: f.name, type: f.type, account_id: Number(f.account_id), transfer_account_id: f.transfer_account_id ? Number(f.transfer_account_id) : null, amount: f.amount,
    category_id: f.category_id ? Number(f.category_id) : null, merchant_name: f.merchant_name || '', payment_method: f.payment_method || '', frequency: f.frequency,
    next_date: f.next_date, end_date: f.end_date || null, auto_create: f.auto_create, active: f.active,
  })
  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/recurring', b) : api.put(`/recurring/${editing.id}`, b)), {
    onSuccess: (r) => { toast.success(r.generated ? `Saved · ${r.generated} past-due transaction(s) created` : 'Saved'); setEditing(null) }, onError: setError,
  })
  const toggle = useLedgerMutation((r) => api.put(`/recurring/${r.id}`, body({ ...r, amount: toInput(r.amount_minor, r.currency), end_date: r.end_date || '', active: !r.active })))
  const remove = useLedgerMutation((id) => api.delete(`/recurring/${id}`), { onSuccess: () => { toast.success('Deleted'); setDeleting(null) } })
  const items = rec.data || []
  return (
    <>
      <PageHead kicker="Automation" title="Recurring transactions" actions={<Button variant="primary" icon={Plus} onClick={() => open(null)}>New recurring</Button>}>
        Salary, rent, SIPs. The background worker creates each transaction on its date – no need to keep the app open.
      </PageHead>
      <Card>
        {rec.isLoading ? <Loading /> : !items.length ? <Empty icon={Repeat} title="Nothing recurring yet" action={<Button variant="primary" icon={Plus} onClick={() => open(null)}>Create one</Button>}>If a bank or statement import already brings these in, you don't need them here – it would double count.</Empty> : (
          <div className="list">
            {items.map((r) => (
              <div key={r.id} className="list-row" style={{ opacity: r.active ? 1 : 0.55 }}>
                <span className="avatar"><Repeat size={16} /></span>
                <div className="grow"><strong>{r.name}</strong> <Badge>{TYPE_LABEL[r.type]}</Badge><div className="faint" style={{ fontSize: 13 }}>{FREQ_LABEL[r.frequency]} · next {longDate(r.next_date)} · {accounts.find((a) => a.id === r.account_id)?.name}{!r.auto_create ? ' · reminder only' : ''}</div></div>
                <Money minor={r.amount_minor} currency={r.currency} />
                <Switch checked={r.active} label={`Active: ${r.name}`} onChange={() => toggle.mutate(r)} />
                <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => open(r)} />
                <Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete" onClick={() => setDeleting(r)} />
              </div>
            ))}
          </div>
        )}
      </Card>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'New recurring transaction' : 'Edit recurring transaction'}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate(body(form)) }}>
          <div className="form-grid">
            <Field label="Name" required className="full"><input className="input" required value={form.name || ''} placeholder="e.g. Salary" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Type"><Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} options={['expense', 'income', 'transfer', 'investment'].map((v) => ({ value: v, label: TYPE_LABEL[v] }))} /></Field>
            <Field label="Amount" required><input className="input" required inputMode="decimal" value={form.amount || ''} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
            <Field label="Account" required><Select value={form.account_id} required onChange={(e) => setForm({ ...form, account_id: e.target.value })} placeholder="Choose…" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
            {form.type === 'transfer' ? <Field label="To account" required><Select value={form.transfer_account_id} required onChange={(e) => setForm({ ...form, transfer_account_id: e.target.value })} placeholder="Choose…" options={accounts.filter((a) => String(a.id) !== form.account_id).map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
              : <Field label="Category"><Select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} placeholder="Auto" options={categoryOptions(categories, form.type === 'income' ? 'income' : 'expense')} /></Field>}
            <Field label="Frequency"><Select value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} options={Object.entries(FREQ_LABEL).map(([value, label]) => ({ value, label }))} /></Field>
            <Field label="Next date" required><input className="input" type="date" required value={form.next_date || ''} onChange={(e) => setForm({ ...form, next_date: e.target.value })} /></Field>
            <Field label="End date"><input className="input" type="date" value={form.end_date || ''} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></Field>
            <Field label="Merchant"><input className="input" value={form.merchant_name || ''} onChange={(e) => setForm({ ...form, merchant_name: e.target.value })} /></Field>
            <label className="checkbox full"><input type="checkbox" checked={form.auto_create} onChange={(e) => setForm({ ...form, auto_create: e.target.checked })} />Create transactions automatically</label>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save</Button></div>
        </form>
      </Modal>
      <Confirm open={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name}?`} message="Transactions it already created are kept." loading={remove.isPending} onConfirm={() => remove.mutate(deleting.id)} />
    </>
  )
}
