import { Paperclip, Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { toInput, todayISO } from '../lib/format'
import { categoryTree, useAccounts, useCategories, useLedgerMutation, useSession, useToast } from '../lib/hooks'
import { Button, Field, FormError, Modal, Segmented, Select } from './ui'

const TYPES = [
  { value: 'expense', label: 'Expense' },
  { value: 'income', label: 'Income' },
  { value: 'transfer', label: 'Transfer' },
  { value: 'refund', label: 'Refund' },
  { value: 'investment', label: 'Invest' },
]
const METHODS = ['UPI', 'Debit card', 'Credit card', 'Cash', 'Net banking', 'Auto-debit', 'Cheque', 'Wallet']

function blank(defaultAccountId, type = 'expense') {
  return {
    type, amount: '', description: '', merchant: '', category_id: '', account_id: defaultAccountId ? String(defaultAccountId) : '',
    date: todayISO(), payment_method: '', tags: '', notes: '', transfer_account_id: '', transfer_amount: '', fx_rate: '',
    is_recurring: false, reviewed: true, splits: null,
  }
}

function fromTxn(t) {
  return {
    type: t.type, amount: toInput(t.amount_minor, t.currency), description: t.description, merchant: t.merchant || '',
    category_id: t.category_id ? String(t.category_id) : '', account_id: String(t.account_id), date: t.date,
    payment_method: t.payment_method || '', tags: t.tags.map((x) => x.name).join(', '), notes: t.notes || '',
    transfer_account_id: t.transfer_account_id ? String(t.transfer_account_id) : '',
    transfer_amount: t.transfer_amount_minor ? toInput(t.transfer_amount_minor) : '', fx_rate: t.fx_rate || '',
    is_recurring: t.is_recurring, reviewed: true,
    splits: t.splits.length ? t.splits.map((s) => ({ category_id: String(s.category_id || ''), amount: toInput(s.amount_minor, t.currency), note: s.note })) : null,
  }
}

export function categoryOptions(categories, kind) {
  return categoryTree(categories, kind).map((p) => ({
    group: p.name,
    options: [{ value: String(p.id), label: `${p.name} (general)` }, ...p.children.map((c) => ({ value: String(c.id), label: c.name }))],
  }))
}

export default function TransactionForm({ open, onClose, transaction, initialType = 'expense' }) {
  const session = useSession()
  const toast = useToast()
  const { data: accounts = [] } = useAccounts()
  const { data: categories = [] } = useCategories()
  const [form, setForm] = useState(() => blank(session.settings.default_account_id, initialType))
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open) return
    setError(null)
    setForm(transaction ? fromTxn(transaction) : blank(session.settings.default_account_id || accounts[0]?.id, initialType))
  }, [open, transaction, initialType]) // eslint-disable-line react-hooks/exhaustive-deps

  const set = (patch) => setForm((f) => ({ ...f, ...patch }))
  const account = accounts.find((a) => String(a.id) === form.account_id)
  const destination = accounts.find((a) => String(a.id) === form.transfer_account_id)
  const foreign = account && account.currency !== session.settings.base_currency
  const kind = form.type === 'income' ? 'income' : 'expense'
  const catOptions = useMemo(() => categoryOptions(categories, kind), [categories, kind])
  const splitTotal = (form.splits || []).reduce((s, p) => s + (Number(p.amount) || 0), 0)

  // Live AI suggestion (on-device ML + entity extraction) while typing.
  const [ai, setAi] = useState(null)
  useEffect(() => {
    if (!open || !['expense', 'income', 'refund'].includes(form.type) || form.description.trim().length < 3) { setAi(null); return undefined }
    const timer = setTimeout(() => {
      api.post('/ai/suggest', { description: form.description, merchant: form.merchant || null, amount: form.amount || null, type: form.type === 'income' ? 'income' : 'expense' })
        .then((r) => {
          setAi(r)
          setForm((f) => ({ ...f, payment_method: f.payment_method || r.payment_method || '' }))
        })
        .catch(() => setAi(null))
    }, 450)
    return () => clearTimeout(timer)
  }, [open, form.description, form.merchant, form.type]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = useLedgerMutation((payload) => (transaction ? api.put(`/transactions/${transaction.id}`, payload) : api.post('/transactions', payload)), {
    onSuccess: (data) => {
      toast.success(transaction ? 'Transaction updated' : 'Transaction added')
      for (const title of data.alerts_triggered || []) toast.show(`🔔 ${title}`)
      onClose()
    },
    onError: setError,
  })

  function submit(e) {
    e.preventDefault()
    setError(null)
    if (!form.account_id) return setError(new Error('Choose an account (add one on the Accounts page first).'))
    const payload = {
      type: form.type, account_id: Number(form.account_id), date: form.date, amount: form.amount, description: form.description.trim(),
      merchant: form.merchant.trim() || null, category_id: form.category_id ? Number(form.category_id) : null, notes: form.notes,
      payment_method: form.payment_method, tags: form.tags.split(',').map((t) => t.trim()).filter(Boolean), is_recurring: form.is_recurring,
      reviewed: true,
    }
    if (form.type === 'transfer') {
      payload.transfer_account_id = form.transfer_account_id ? Number(form.transfer_account_id) : null
      if (destination && account && destination.currency !== account.currency) payload.transfer_amount = form.transfer_amount
      payload.category_id = null
      payload.merchant = null
    }
    if (foreign && form.fx_rate) payload.fx_rate = form.fx_rate
    if (form.splits) payload.splits = form.splits.map((s) => ({ category_id: s.category_id ? Number(s.category_id) : null, amount: s.amount, note: s.note || '' }))
    save.mutate(payload)
  }

  const accountOptions = accounts.filter((a) => !a.is_archived).map((a) => ({ value: String(a.id), label: `${a.name}${a.currency !== session.settings.base_currency ? ` (${a.currency})` : ''}` }))

  return (
    <Modal open={open} onClose={onClose} kicker={transaction ? 'Edit' : 'Quick add'} title={transaction ? 'Edit transaction' : 'Add transaction'}>
      <form onSubmit={submit} className="stack">
        <Segmented label="Transaction type" value={form.type} onChange={(type) => set({ type, category_id: '' })} options={form.type === 'adjustment' ? [...TYPES, { value: 'adjustment', label: 'Adjustment' }] : TYPES} />
        <div className="form-grid">
          <Field label={`Amount${account ? ` (${account.currency})` : ''}`} required className="full">
            <input className="input amount" inputMode="decimal" required autoFocus placeholder="0.00" value={form.amount} onChange={(e) => set({ amount: e.target.value.replace(/[^0-9.,-]/g, '') })} aria-label="Amount" />
          </Field>
          <Field label="Description" required className="full">
            <input className="input" required maxLength={255} value={form.description} placeholder={form.type === 'income' ? 'e.g. September salary' : form.type === 'transfer' ? 'e.g. Move to savings' : 'e.g. Groceries at DMart'} onChange={(e) => set({ description: e.target.value })} />
          </Field>
          {form.type !== 'transfer' && form.type !== 'adjustment' && (
            <>
              <Field label="Merchant"><input className="input" value={form.merchant} placeholder="e.g. Swiggy" onChange={(e) => set({ merchant: e.target.value })} /></Field>
              <Field label="Category" hint={form.splits ? 'Using splits below' : 'Leave empty to auto-categorise'}>
                <Select value={form.category_id} disabled={!!form.splits} onChange={(e) => set({ category_id: e.target.value })} placeholder="Auto (AI)" options={catOptions} />
              </Field>
              {ai && (ai.suggestions.length > 0 || ai.summary) && !form.splits && (
                <div className="full">
                  {ai.summary && <div className="entity-chips">{ai.summary.split(' · ').map((part) => <span key={part}>{part}</span>)}</div>}
                  {ai.suggestions.length > 0 && !form.category_id && (
                    <div className="suggest-chips" aria-label="Suggested categories">
                      <span className="ai-badge">✦ AI suggests</span>
                      {ai.suggestions.map((sug) => (
                        <button key={sug.category_id} type="button" onClick={() => set({ category_id: String(sug.category_id), merchant: form.merchant || ai.merchant || '' })}>
                          {sug.category.split('/').pop()} · {Math.round(sug.confidence * 100)}%
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
          <Field label={form.type === 'transfer' ? 'From account' : 'Account'} required>
            <Select value={form.account_id} required onChange={(e) => set({ account_id: e.target.value })} placeholder="Choose…" options={accountOptions} />
          </Field>
          {form.type === 'transfer' ? (
            <Field label="To account" required>
              <Select value={form.transfer_account_id} required onChange={(e) => set({ transfer_account_id: e.target.value })} placeholder="Choose…" options={accountOptions.filter((o) => o.value !== form.account_id)} />
            </Field>
          ) : (
            <Field label="Date" required><input className="input" type="date" required value={form.date} onChange={(e) => set({ date: e.target.value })} /></Field>
          )}
          {form.type === 'transfer' && <Field label="Date" required><input className="input" type="date" required value={form.date} onChange={(e) => set({ date: e.target.value })} /></Field>}
          {form.type === 'transfer' && destination && account && destination.currency !== account.currency && (
            <Field label={`Amount received (${destination.currency})`} required><input className="input" inputMode="decimal" required value={form.transfer_amount} onChange={(e) => set({ transfer_amount: e.target.value })} /></Field>
          )}
          {foreign && (
            <Field label={`Rate: 1 ${account.currency} = ? ${session.settings.base_currency}`} hint="Leave empty to use the latest saved rate">
              <input className="input" inputMode="decimal" value={form.fx_rate} onChange={(e) => set({ fx_rate: e.target.value })} />
            </Field>
          )}
        </div>

        <details className="advanced" open={!!(form.splits || form.notes || form.tags)}>
          <summary>More options</summary>
          <div className="form-grid" style={{ marginTop: 10 }}>
            <Field label="Payment method"><Select value={form.payment_method} onChange={(e) => set({ payment_method: e.target.value })} placeholder="—" options={METHODS.map((m) => ({ value: m, label: m }))} /></Field>
            <Field label="Tags" hint="Comma separated"><input className="input" value={form.tags} placeholder="work, trip-goa" onChange={(e) => set({ tags: e.target.value })} /></Field>
            <Field label="Notes" className="full"><textarea className="input" rows={2} value={form.notes} onChange={(e) => set({ notes: e.target.value })} /></Field>
            <label className="checkbox"><input type="checkbox" checked={form.is_recurring} onChange={(e) => set({ is_recurring: e.target.checked })} />Recurring</label>
            {!transaction && <label className="checkbox"><input type="checkbox" checked={form.type === 'adjustment'} onChange={(e) => set({ type: e.target.checked ? 'adjustment' : 'expense' })} />Balance adjustment</label>}
            {['expense', 'income', 'refund'].includes(form.type) && (
              <div className="full stack" style={{ gap: 8 }}>
                <div className="row between">
                  <strong style={{ fontSize: 13 }}>Split across categories</strong>
                  {form.splits ? <Button size="sm" variant="ghost" onClick={() => set({ splits: null })}>Remove split</Button>
                    : <Button size="sm" icon={Plus} onClick={() => set({ splits: [{ category_id: form.category_id, amount: form.amount, note: '' }, { category_id: '', amount: '', note: '' }] })}>Split</Button>}
                </div>
                {form.splits?.map((part, i) => (
                  <div key={i} className="row">
                    <Select value={part.category_id} onChange={(e) => set({ splits: form.splits.map((p, j) => (j === i ? { ...p, category_id: e.target.value } : p)) })} placeholder="Category" options={catOptions} />
                    <input className="input" style={{ width: 120 }} inputMode="decimal" placeholder="0.00" value={part.amount} onChange={(e) => set({ splits: form.splits.map((p, j) => (j === i ? { ...p, amount: e.target.value } : p)) })} aria-label="Split amount" />
                    <Button variant="ghost" icon={Trash2} aria-label="Remove part" disabled={form.splits.length <= 2} onClick={() => set({ splits: form.splits.filter((_, j) => j !== i) })} />
                  </div>
                ))}
                {form.splits && (
                  <div className="row between">
                    <Button size="sm" icon={Plus} onClick={() => set({ splits: [...form.splits, { category_id: '', amount: '', note: '' }] })}>Add part</Button>
                    <span className={`num ${Math.abs(splitTotal - Number(form.amount || 0)) > 0.001 ? 'expense' : 'income'}`} style={{ fontSize: 13 }}>{splitTotal.toFixed(2)} / {Number(form.amount || 0).toFixed(2)}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </details>

        {transaction && <Attachments transaction={transaction} />}
        <FormError error={error} />
        <div className="modal-foot" style={{ marginTop: 4 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={save.isPending}>{transaction ? 'Save changes' : 'Add transaction'}</Button>
        </div>
      </form>
    </Modal>
  )
}

function Attachments({ transaction }) {
  const toast = useToast()
  const [items, setItems] = useState(transaction.attachments || [])
  const [busy, setBusy] = useState(false)
  async function upload(file) {
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    setBusy(true)
    try {
      const att = await api.upload(`/transactions/${transaction.id}/attachments`, form)
      setItems((x) => [...x, att])
      toast.success('Receipt attached')
    } catch (e) {
      toast.error(e.message)
    } finally {
      setBusy(false)
    }
  }
  async function remove(att) {
    await api.delete(`/attachments/${att.id}`)
    setItems((x) => x.filter((a) => a.id !== att.id))
  }
  return (
    <div className="stack" style={{ gap: 8 }}>
      <strong style={{ fontSize: 13 }}>Receipts</strong>
      {items.map((att) => (
        <div key={att.id} className="row">
          <Paperclip size={15} className="faint" />
          <a className="grow truncate" href={`/api/attachments/${att.id}`} target="_blank" rel="noreferrer">{att.filename}</a>
          <span className="faint" style={{ fontSize: 12 }}>{Math.round(att.size_bytes / 1024)} KB</span>
          <Button size="sm" variant="ghost" icon={Trash2} aria-label="Remove receipt" onClick={() => remove(att)} />
        </div>
      ))}
      <label className="btn sm" style={{ alignSelf: 'flex-start' }} aria-busy={busy}>
        <Paperclip size={15} /> {busy ? 'Uploading…' : 'Attach JPG, PNG or PDF'}
        <input type="file" hidden accept="image/jpeg,image/png,application/pdf" onChange={(e) => upload(e.target.files?.[0])} />
      </label>
    </div>
  )
}
