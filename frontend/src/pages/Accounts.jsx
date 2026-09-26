import { Archive, CreditCard, Landmark, Pencil, Plus, Scale, Trash2, Wallet } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Badge, Button, Card, Empty, ErrorNote, Field, FormError, Loading, Modal, Money, PageHead, Select } from '../components/ui'
import { api } from '../lib/api'
import { ACCOUNT_LABEL, money, relativeTime, toInput } from '../lib/format'
import { useAccounts, useLedgerMutation, useSession, useToast } from '../lib/hooks'

const TYPES = Object.entries(ACCOUNT_LABEL).map(([value, label]) => ({ value, label }))
const LIABILITY = ['credit_card', 'loan', 'mortgage', 'liability']
const GROUPS = [
  { label: 'Cash & bank', types: ['current', 'savings', 'cash', 'wallet'] },
  { label: 'Credit cards', types: ['credit_card'] },
  { label: 'Investments & assets', types: ['investment', 'asset'] },
  { label: 'Loans & liabilities', types: ['loan', 'mortgage', 'liability'] },
]

export function useNewParam(open) {
  const [params, setParams] = useSearchParams()
  useEffect(() => {
    if (params.get('new')) { open(); params.delete('new'); setParams(params, { replace: true }) }
  }, [params]) // eslint-disable-line react-hooks/exhaustive-deps
}

function empty(currency) {
  return { name: '', type: 'savings', institution: '', currency, opening_balance: '0', opening_date: '', credit_limit: '', account_number_mask: '', include_in_net_worth: true, is_archived: false }
}

export default function Accounts() {
  const session = useSession()
  const toast = useToast()
  const accounts = useAccounts()
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(empty(session.settings.base_currency))
  const [error, setError] = useState(null)
  const [confirm, setConfirm] = useState(null)
  const cur = session.settings.base_currency

  const openNew = () => { setForm(empty(cur)); setEditing('new'); setError(null) }
  useNewParam(openNew)
  const openEdit = (a) => {
    setForm({
      name: a.name, type: a.type, institution: a.institution, currency: a.currency,
      opening_balance: toInput(LIABILITY.includes(a.type) ? Math.abs(a.opening_balance_minor) : a.opening_balance_minor, a.currency),
      opening_date: a.opening_date || '', credit_limit: a.credit_limit_minor != null ? toInput(a.credit_limit_minor, a.currency) : '',
      account_number_mask: a.account_number_mask, include_in_net_worth: a.include_in_net_worth, is_archived: a.is_archived,
    })
    setEditing(a)
    setError(null)
  }
  const save = useLedgerMutation((body) => (editing === 'new' ? api.post('/accounts', body) : api.put(`/accounts/${editing.id}`, body)), {
    onSuccess: () => { toast.success(editing === 'new' ? 'Account added' : 'Account updated'); setEditing(null) },
    onError: setError,
  })
  const remove = useLedgerMutation(({ id, confirmDelete }) => api.delete(`/accounts/${id}`, confirmDelete ? { confirm: true } : undefined), {
    onSuccess: (r) => { toast.success(`Account deleted${r.transactions_deleted ? ` with ${r.transactions_deleted} transactions` : ''}`); setConfirm(null) },
    onError: (e) => (e.status === 409 ? setConfirm((c) => ({ ...c, needsConfirm: e.message })) : toast.error(e.message)),
  })
  const archive = useLedgerMutation((a) => api.put(`/accounts/${a.id}`, { ...editBody(a), is_archived: true }), { onSuccess: () => { toast.success('Account archived'); setConfirm(null) } })

  const submit = (e) => {
    e.preventDefault()
    setError(null)
    save.mutate({ ...form, opening_date: form.opening_date || null, credit_limit: form.credit_limit || null, opening_balance: form.opening_balance || '0' })
  }
  const list = accounts.data || []
  const liability = LIABILITY.includes(form.type)

  return (
    <>
      <PageHead kicker="Your money" title="Accounts" actions={<Button variant="primary" icon={Plus} onClick={openNew}>Add account</Button>}>
        Balances are computed from each account's opening balance plus its transactions, so they always match the ledger.
      </PageHead>
      <ErrorNote error={accounts.error} onRetry={accounts.refetch} />
      {accounts.isLoading ? <Loading /> : list.length === 0 ? (
        <Card><Empty icon={Wallet} title="Add your first account" action={<Button variant="primary" icon={Plus} onClick={openNew}>Add account</Button>}>A bank account, cash wallet, credit card, loan or investment. You can also <Link to="/banks">connect a bank</Link>.</Empty></Card>
      ) : GROUPS.map((g) => {
        const rows = list.filter((a) => g.types.includes(a.type))
        if (!rows.length) return null
        const total = rows.reduce((s, a) => s + (a.base_balance_minor ?? 0), 0)
        return (
          <section key={g.label} style={{ marginBottom: 22 }}>
            <div className="row between" style={{ margin: '0 4px 10px' }}><h3 style={{ margin: 0, fontSize: 15 }}>{g.label}</h3><Money minor={total} currency={cur} className="muted" /></div>
            <div className="cards">
              {rows.map((a) => (
                <Card key={a.id} hover>
                  <div className="row between">
                    <span className="avatar">{a.type === 'credit_card' ? <CreditCard size={17} /> : LIABILITY.includes(a.type) ? <Scale size={17} /> : <Landmark size={17} />}</span>
                    <div className="row" style={{ gap: 2 }}>
                      <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${a.name}`} onClick={() => openEdit(a)} />
                      <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Delete ${a.name}`} onClick={() => setConfirm({ account: a })} />
                    </div>
                  </div>
                  <h3 style={{ margin: '12px 0 2px' }}>{a.name}</h3>
                  <div className="faint" style={{ fontSize: 13 }}>{ACCOUNT_LABEL[a.type]}{a.institution ? ` · ${a.institution}` : ''}{a.account_number_mask ? ` · ••${a.account_number_mask}` : ''}</div>
                  <div className="num" style={{ fontSize: 24, fontWeight: 700, marginTop: 12 }}>{LIABILITY.includes(a.type) && a.balance_minor < 0 ? <span className="expense">{money(-a.balance_minor, a.currency)} owed</span> : money(a.balance_minor, a.currency)}</div>
                  {a.currency !== cur && <div className="faint" style={{ fontSize: 12 }}>{a.base_balance_minor != null ? `≈ ${money(a.base_balance_minor, cur)}` : 'No exchange rate – excluded from totals'}</div>}
                  {a.type === 'credit_card' && a.available_minor != null && <div className="faint" style={{ fontSize: 13, marginTop: 4 }}>Available {money(a.available_minor, a.currency)} of {money(a.credit_limit_minor, a.currency)}</div>}
                  <div className="row wrap" style={{ marginTop: 10, gap: 6 }}>
                    {a.bank_connection_id && <Badge tone={a.connection_status === 'active' ? 'success' : 'warning'}>Linked · synced {relativeTime(a.last_synced_at)}</Badge>}
                    {!a.include_in_net_worth && <Badge>not in net worth</Badge>}
                    {a.reconciliation && a.reconciliation.difference !== 0 && <Badge tone="warning">Bank says {money(a.reconciliation.reported, a.currency)} ({money(a.reconciliation.difference, a.currency, { sign: true })})</Badge>}
                  </div>
                  <Link to={`/transactions?account_id=${a.id}`} className="faint" style={{ display: 'inline-block', marginTop: 12, fontSize: 13 }}>View transactions →</Link>
                </Card>
              ))}
            </div>
          </section>
        )
      })}

      <Modal open={!!editing} onClose={() => setEditing(null)} kicker={editing === 'new' ? 'New' : 'Edit'} title={editing === 'new' ? 'Add account' : `Edit ${editing?.name || ''}`}>
        <form onSubmit={submit} className="stack">
          <div className="form-grid">
            <Field label="Name" required className="full"><input className="input" required value={form.name} placeholder="e.g. HDFC Savings" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Type"><Select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} options={TYPES} /></Field>
            <Field label="Institution"><input className="input" value={form.institution} placeholder="e.g. HDFC Bank" onChange={(e) => setForm({ ...form, institution: e.target.value })} /></Field>
            <Field label={liability ? 'Amount owed at start' : 'Opening balance'} hint={liability ? 'Enter as a positive number' : 'Balance before the first transaction you record'}>
              <input className="input" inputMode="decimal" value={form.opening_balance} onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} />
            </Field>
            <Field label="Opening date" hint="Optional: used for historical net worth"><input className="input" type="date" value={form.opening_date} onChange={(e) => setForm({ ...form, opening_date: e.target.value })} /></Field>
            <Field label="Currency" hint={form.currency !== cur ? `Totals need a ${form.currency}→${cur} rate (Settings)` : undefined}>
              <Select value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} options={['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD'].map((c) => ({ value: c, label: c }))} />
            </Field>
            {form.type === 'credit_card' && <Field label="Credit limit"><input className="input" inputMode="decimal" value={form.credit_limit} onChange={(e) => setForm({ ...form, credit_limit: e.target.value })} /></Field>}
            <Field label="Last 4 digits"><input className="input" maxLength={4} inputMode="numeric" value={form.account_number_mask} onChange={(e) => setForm({ ...form, account_number_mask: e.target.value.replace(/\D/g, '') })} /></Field>
            <label className="checkbox full"><input type="checkbox" checked={form.include_in_net_worth} onChange={(e) => setForm({ ...form, include_in_net_worth: e.target.checked })} />Include in net worth</label>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save</Button></div>
        </form>
      </Modal>

      <Modal open={!!confirm} onClose={() => setConfirm(null)} title={`Delete ${confirm?.account?.name}?`} footer={<>
        <Button onClick={() => setConfirm(null)}>Cancel</Button>
        {confirm?.needsConfirm && <Button icon={Archive} onClick={() => archive.mutate(confirm.account)}>Archive instead</Button>}
        <Button variant="danger solid" loading={remove.isPending} onClick={() => remove.mutate({ id: confirm.account.id, confirmDelete: !!confirm.needsConfirm })}>{confirm?.needsConfirm ? 'Delete everything' : 'Delete'}</Button>
      </>}>
        <p className="muted" style={{ margin: 0 }}>{confirm?.needsConfirm || 'The account will be removed.'}</p>
      </Modal>
    </>
  )
}

function editBody(a) {
  return {
    name: a.name, type: a.type, institution: a.institution, currency: a.currency,
    opening_balance: toInput(LIABILITY.includes(a.type) ? Math.abs(a.opening_balance_minor) : a.opening_balance_minor, a.currency),
    opening_date: a.opening_date, credit_limit: a.credit_limit_minor != null ? toInput(a.credit_limit_minor, a.currency) : null,
    account_number_mask: a.account_number_mask, include_in_net_worth: a.include_in_net_worth,
  }
}
