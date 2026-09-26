import { useQuery } from '@tanstack/react-query'
import { CreditCard, Pencil, Plus, Radar, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Field, FormError, Loading, Modal, Money, PageHead, Select } from '../components/ui'
import { api } from '../lib/api'
import { FREQ_LABEL, longDate, money, toInput, todayISO } from '../lib/format'
import { useAccounts, useCategories, useLedgerMutation, useSession, useToast } from '../lib/hooks'

const FREQS = Object.entries(FREQ_LABEL).filter(([k]) => k !== 'once').map(([value, label]) => ({ value, label }))

export default function Subscriptions() {
  const session = useSession()
  const toast = useToast()
  const cur = session.settings.base_currency
  const { data: accounts = [] } = useAccounts()
  const { data: categories = [] } = useCategories()
  const subs = useQuery({ queryKey: ['subscriptions'], queryFn: () => api.get('/subscriptions') })
  const detected = useQuery({ queryKey: ['subscriptions-detected'], queryFn: () => api.get('/subscriptions/detected') })
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)

  const open = (s, prefill) => {
    setError(null)
    setEditing(s || 'new')
    setForm(s ? { name: s.name, merchant: s.merchant || '', amount: toInput(s.amount_minor, s.currency), frequency: s.frequency, next_payment_date: s.next_payment_date || '', account_id: s.account_id ? String(s.account_id) : '', category_id: s.category_id ? String(s.category_id) : '', active: s.active, started_on: s.started_on || '', notes: s.notes, detected: s.detected }
      : { name: '', merchant: '', amount: '', frequency: 'monthly', next_payment_date: todayISO(), account_id: '', category_id: '', active: true, started_on: '', notes: '', detected: false, ...prefill })
  }
  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/subscriptions', b) : api.put(`/subscriptions/${editing.id}`, b)), { onSuccess: () => { toast.success('Subscription saved'); setEditing(null) }, onError: setError })
  const remove = useLedgerMutation((id) => api.delete(`/subscriptions/${id}`), { onSuccess: () => { toast.success('Deleted'); setDeleting(null) } })
  const toggle = useLedgerMutation((s) => api.put(`/subscriptions/${s.id}`, { name: s.name, merchant: s.merchant, amount: toInput(s.amount_minor, s.currency), currency: s.currency, frequency: s.frequency, next_payment_date: s.next_payment_date, account_id: s.account_id, category_id: s.category_id, active: !s.active, started_on: s.started_on, notes: s.notes, detected: s.detected }))

  const items = subs.data?.items || []
  const totals = subs.data?.totals

  return (
    <>
      <PageHead kicker="Plan" title="Subscriptions" actions={<Button variant="primary" icon={Plus} onClick={() => open(null)}>Add subscription</Button>}>
        Recurring services. When a charge from the same merchant appears, the next payment date rolls forward and price changes are flagged.
      </PageHead>
      {totals && (
        <div className="grid grid-3" style={{ marginBottom: 16 }}>
          <Card className="stat"><div className="label">Per month</div><div className="value"><Money minor={totals.monthly} currency={cur} animated /></div><div className="meta">{totals.active_count} active</div></Card>
          <Card className="stat"><div className="label">Per year</div><div className="value"><Money minor={totals.annual} currency={cur} animated /></div><div className="meta">annual equivalent</div></Card>
          <Card className="stat"><div className="label">Most expensive</div><div className="value" style={{ fontSize: 20 }}>{[...items].filter((s) => s.active).sort((a, b) => b.monthly_equivalent_minor - a.monthly_equivalent_minor)[0]?.name || '—'}</div></Card>
        </div>
      )}
      {detected.data?.length > 0 && (
        <Card title="Detected from your transactions" sub="Regular charges with a stable amount – confirm to track them" action={<Radar size={16} className="faint" />} style={{ marginBottom: 16 }}>
          <div className="list">
            {detected.data.map((d) => (
              <div key={d.merchant_id} className="list-row">
                <span className="avatar">{d.name[0]}</span>
                <div className="grow"><strong>{d.name}</strong><div className="faint" style={{ fontSize: 13 }}>{FREQ_LABEL[d.frequency]} · {d.occurrences} charges · last {longDate(d.last_charged)}{d.price_changed ? ' · price changed' : ''}</div></div>
                <Money minor={d.amount_minor} currency={d.currency} />
                <Button size="sm" icon={Plus} onClick={() => open(null, { name: d.name, merchant: d.name, amount: toInput(d.amount_minor, d.currency), frequency: d.frequency, next_payment_date: d.next_expected, account_id: d.account_id ? String(d.account_id) : '', category_id: d.category_id ? String(d.category_id) : '', detected: true })}>Track</Button>
              </div>
            ))}
          </div>
        </Card>
      )}
      <ErrorNote error={subs.error} onRetry={subs.refetch} />
      <Card>
        {subs.isLoading ? <Loading /> : !items.length ? <Empty icon={CreditCard} title="No subscriptions tracked">Add Netflix, Spotify, cloud storage… or wait for detection once a few months of transactions exist.</Empty> : (
          <div className="table-wrap"><table className="table">
            <thead><tr><th>Service</th><th>Frequency</th><th className="hide-mobile">Next payment</th><th className="amount">Price</th><th className="amount hide-mobile">Per month</th><th className="amount hide-mobile">Per year</th><th /></tr></thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} style={{ opacity: s.active ? 1 : 0.5 }}>
                  <td><strong>{s.name}</strong> {!s.active && <Badge>cancelled</Badge>} {s.previous_amount_minor != null && <Badge tone="warning">was {money(s.previous_amount_minor, s.currency)}</Badge>}</td>
                  <td>{FREQ_LABEL[s.frequency]}</td>
                  <td className="hide-mobile">{s.next_payment_date ? longDate(s.next_payment_date) : '—'}</td>
                  <td className="amount">{money(s.amount_minor, s.currency)}</td>
                  <td className="amount hide-mobile">{money(s.monthly_equivalent_minor, s.currency)}</td>
                  <td className="amount hide-mobile">{money(s.annual_equivalent_minor, s.currency)}</td>
                  <td><div className="row" style={{ gap: 2, justifyContent: 'flex-end' }}>
                    <Button size="sm" variant="ghost" onClick={() => toggle.mutate(s)}>{s.active ? 'Cancel' : 'Resume'}</Button>
                    <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => open(s)} />
                    <Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete" onClick={() => setDeleting(s)} />
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'Add subscription' : 'Edit subscription'}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate({ ...form, account_id: form.account_id ? Number(form.account_id) : null, category_id: form.category_id ? Number(form.category_id) : null, next_payment_date: form.next_payment_date || null, started_on: form.started_on || null }) }}>
          <div className="form-grid">
            <Field label="Service" required><input className="input" required value={form.name || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Merchant (as it appears on statements)"><input className="input" value={form.merchant || ''} onChange={(e) => setForm({ ...form, merchant: e.target.value })} /></Field>
            <Field label="Price" required><input className="input" required inputMode="decimal" value={form.amount || ''} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></Field>
            <Field label="Frequency"><Select value={form.frequency} onChange={(e) => setForm({ ...form, frequency: e.target.value })} options={FREQS} /></Field>
            <Field label="Next payment"><input className="input" type="date" value={form.next_payment_date || ''} onChange={(e) => setForm({ ...form, next_payment_date: e.target.value })} /></Field>
            <Field label="Account"><Select value={form.account_id} onChange={(e) => setForm({ ...form, account_id: e.target.value })} placeholder="—" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
            <Field label="Category"><Select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} placeholder="—" options={categoryOptions(categories, 'expense')} /></Field>
            <label className="checkbox"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} />Active</label>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save</Button></div>
        </form>
      </Modal>
      <Confirm open={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name}?`} message="Only the tracking is removed; past transactions stay." loading={remove.isPending} onConfirm={() => remove.mutate(deleting.id)} />
    </>
  )
}
