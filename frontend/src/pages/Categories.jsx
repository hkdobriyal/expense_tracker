import { useQuery } from '@tanstack/react-query'
import { Eye, Pencil, Play, Plus, Shapes, Trash2, Wand2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Empty, Field, FormError, Loading, Modal, Money, PageHead, Segmented, Select, Switch } from '../components/ui'
import { api } from '../lib/api'
import { money, shortDate, toInput } from '../lib/format'
import { categoryTree, useAccounts, useCategories, useLedgerMutation, useSession, useToast } from '../lib/hooks'

export default function Categories() {
  const [tab, setTab] = useState('categories')
  return (
    <>
      <PageHead kicker="Organise" title="Categories, rules & merchants">
        Categories have two levels. Rules categorise new transactions automatically – first match wins, in priority order.
      </PageHead>
      <div style={{ marginBottom: 16 }}><Segmented label="Section" value={tab} onChange={setTab} options={[{ value: 'categories', label: 'Categories' }, { value: 'rules', label: 'Smart rules' }, { value: 'merchants', label: 'Merchants' }]} /></div>
      {tab === 'categories' && <CategoryTree />}
      {tab === 'rules' && <Rules />}
      {tab === 'merchants' && <Merchants />}
    </>
  )
}

function CategoryTree() {
  const toast = useToast()
  const { data: categories = [], isLoading } = useCategories()
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const [reassign, setReassign] = useState('')
  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/categories', b) : api.put(`/categories/${editing.id}`, b)), { onSuccess: () => { toast.success('Category saved'); setEditing(null) }, onError: setError })
  const remove = useLedgerMutation(() => api.delete(`/categories/${deleting.id}`, reassign ? { reassign_to: reassign } : undefined), { onSuccess: (r) => { toast.success(`Deleted · ${r.transactions_updated} transactions updated`); setDeleting(null) } })
  const open = (cat, parent) => {
    setError(null)
    setEditing(cat || 'new')
    setForm(cat ? { name: cat.name, parent_id: cat.parent_id ? String(cat.parent_id) : '', kind: cat.kind, color: cat.color || '#8ae6ff', icon: cat.icon, is_archived: cat.is_archived }
      : { name: '', parent_id: parent ? String(parent.id) : '', kind: parent?.kind || 'expense', color: parent?.color || '#8ae6ff', icon: '', is_archived: false })
  }
  if (isLoading) return <Loading />
  return (
    <>
      <div className="row" style={{ marginBottom: 14 }}><Button variant="primary" icon={Plus} onClick={() => open(null)}>New category</Button></div>
      <div className="grid grid-2">
        {['expense', 'income'].map((kind) => (
          <Card key={kind} title={kind === 'expense' ? 'Expense categories' : 'Income categories'}>
            <div className="list">
              {categoryTree(categories, kind).map((p) => (
                <div key={p.id} style={{ borderBottom: '1px solid var(--border)', padding: '8px 0' }}>
                  <div className="row">
                    <span className="dot" style={{ background: p.color || 'var(--text-3)' }} />
                    <strong className="grow">{p.name}</strong>
                    <Link className="faint" style={{ fontSize: 12 }} to={`/transactions?category_id=${p.id}`}>transactions</Link>
                    <Button size="sm" variant="ghost" icon={Plus} aria-label={`Add subcategory to ${p.name}`} onClick={() => open(null, p)} />
                    <Button size="sm" variant="ghost" icon={Pencil} aria-label={`Edit ${p.name}`} onClick={() => open(p)} />
                    <Button size="sm" variant="ghost" icon={Trash2} aria-label={`Delete ${p.name}`} onClick={() => { setDeleting(p); setReassign('') }} />
                  </div>
                  {p.children.length > 0 && (
                    <div className="row wrap" style={{ gap: 6, padding: '8px 0 2px 19px' }}>
                      {p.children.map((c) => (
                        <span key={c.id} className="badge" style={{ cursor: 'pointer' }} role="button" tabIndex={0} onClick={() => open(c)} onKeyDown={(e) => e.key === 'Enter' && open(c)}>{c.name}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'New category' : 'Edit category'}>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate({ ...form, parent_id: form.parent_id ? Number(form.parent_id) : null }) }}>
          <div className="form-grid">
            <Field label="Name" required className="full"><input className="input" required value={form.name || ''} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Kind"><Select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value, parent_id: '' })} options={[{ value: 'expense', label: 'Expense' }, { value: 'income', label: 'Income' }]} /></Field>
            <Field label="Parent"><Select value={form.parent_id} onChange={(e) => setForm({ ...form, parent_id: e.target.value })} placeholder="None (top level)" options={categoryTree(categories, form.kind).filter((p) => p.id !== editing?.id).map((p) => ({ value: String(p.id), label: p.name }))} /></Field>
            <Field label="Colour"><input className="input" type="color" value={form.color || '#8ae6ff'} onChange={(e) => setForm({ ...form, color: e.target.value })} style={{ padding: 4, height: 40 }} /></Field>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save</Button></div>
        </form>
      </Modal>
      <Modal open={!!deleting} onClose={() => setDeleting(null)} title={`Delete ${deleting?.name}?`} footer={<><Button onClick={() => setDeleting(null)}>Cancel</Button><Button variant="danger solid" loading={remove.isPending} onClick={() => remove.mutate()}>Delete</Button></>}>
        <p className="muted">Subcategories are deleted too. Move their transactions to:</p>
        <Select value={reassign} onChange={(e) => setReassign(e.target.value)} placeholder="Leave uncategorised" options={categoryOptions(categories.filter((c) => c.id !== deleting?.id && c.parent_id !== deleting?.id), deleting?.kind)} />
      </Modal>
    </>
  )
}

const MATCH = [['contains', 'contains'], ['equals', 'equals'], ['starts_with', 'starts with'], ['ends_with', 'ends with'], ['regex', 'matches regex']]
const FIELDS = [['any', 'Any text'], ['description', 'Description'], ['merchant', 'Merchant'], ['notes', 'Notes']]

function Rules() {
  const toast = useToast()
  const session = useSession()
  const { data: categories = [] } = useCategories()
  const { data: accounts = [] } = useAccounts()
  const rules = useQuery({ queryKey: ['rules'], queryFn: () => api.get('/rules') })
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({})
  const [error, setError] = useState(null)
  const [preview, setPreview] = useState(null)
  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/rules', b) : api.put(`/rules/${editing.id}`, b)), { onSuccess: () => { toast.success('Rule saved'); setEditing(null) }, onError: setError })
  const remove = useLedgerMutation((id) => api.delete(`/rules/${id}`), { onSuccess: () => toast.success('Rule deleted') })
  const apply = useLedgerMutation((id) => api.post(`/rules/${id}/apply`), { onSuccess: (r) => toast.success(`${r.updated} uncategorised transaction(s) updated`) })
  const toggle = useLedgerMutation((r) => api.put(`/rules/${r.id}`, ruleBody(r, { enabled: !r.enabled })))
  const cat = (id) => categories.find((c) => c.id === id)?.name
  const open = (r) => {
    setError(null)
    setEditing(r || 'new')
    setForm(r ? { ...r, amount_min: r.amount_min_minor != null ? toInput(r.amount_min_minor) : '', amount_max: r.amount_max_minor != null ? toInput(r.amount_max_minor) : '', add_tags: '' }
      : { name: '', priority: 100, field: 'any', match_type: 'contains', pattern: '', case_sensitive: false, amount_min: '', amount_max: '', account_id: '', transaction_type: '', set_category_id: '', set_merchant_name: '', add_tags: '', mark_reviewed: true, enabled: true })
  }
  const submit = (e) => {
    e.preventDefault()
    save.mutate({
      name: form.name, priority: Number(form.priority) || 100, field: form.field, match_type: form.match_type, pattern: form.pattern, case_sensitive: form.case_sensitive,
      amount_min: form.amount_min || null, amount_max: form.amount_max || null, account_id: form.account_id ? Number(form.account_id) : null,
      transaction_type: form.transaction_type || null, set_category_id: form.set_category_id ? Number(form.set_category_id) : null,
      set_merchant_name: form.set_merchant_name || null, add_tags: String(form.add_tags || '').split(',').map((t) => t.trim()).filter(Boolean),
      mark_reviewed: form.mark_reviewed, enabled: form.enabled,
    })
  }
  return (
    <>
      <div className="row" style={{ marginBottom: 14 }}><Button variant="primary" icon={Plus} onClick={() => open(null)}>New rule</Button></div>
      <Card>
        {rules.isLoading ? <Loading /> : !rules.data?.length ? (
          <Empty icon={Wand2} title="No rules yet" action={<Button variant="primary" icon={Plus} onClick={() => open(null)}>Create a rule</Button>}>
            Example: when the merchant contains “DMart”, set category Groceries. Imported and synced transactions are categorised automatically.
          </Empty>
        ) : (
          <div className="list">
            {rules.data.map((r) => (
              <div key={r.id} className="list-row" style={{ opacity: r.enabled ? 1 : 0.55 }}>
                <Badge>{r.priority}</Badge>
                <div className="grow">
                  <div style={{ fontWeight: 600 }}>{r.name || `${FIELDS.find((f) => f[0] === r.field)[1]} ${MATCH.find((m) => m[0] === r.match_type)[1]} “${r.pattern}”`}</div>
                  <div className="faint" style={{ fontSize: 13 }}>
                    → {[r.set_category_id && `category ${cat(r.set_category_id)}`, r.set_merchant_name && `merchant ${r.set_merchant_name}`, r.mark_reviewed && 'mark reviewed'].filter(Boolean).join(', ')}
                    {r.amount_min_minor != null && ` · ≥ ${money(r.amount_min_minor, session.settings.base_currency)}`}{r.amount_max_minor != null && ` · ≤ ${money(r.amount_max_minor, session.settings.base_currency)}`}
                    {' · '}applied {r.apply_count}×
                  </div>
                </div>
                <Switch checked={r.enabled} label={`Enable ${r.pattern}`} onChange={() => toggle.mutate(r)} />
                <Button size="sm" variant="ghost" icon={Eye} aria-label="Preview matches" onClick={async () => setPreview({ rule: r, ...(await api.post(`/rules/${r.id}/preview`)) })} />
                <Button size="sm" variant="ghost" icon={Play} aria-label="Apply to uncategorised" onClick={() => apply.mutate(r.id)} />
                <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => open(r)} />
                <Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete" onClick={() => remove.mutate(r.id)} />
              </div>
            ))}
          </div>
        )}
      </Card>
      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing === 'new' ? 'New rule' : 'Edit rule'} wide>
        <form className="stack" onSubmit={submit}>
          <div className="notice info"><div><strong>When</strong>the selected text matches the pattern (and the optional conditions hold), <strong style={{ display: 'inline' }}>then</strong> apply the actions.</div></div>
          <div className="form-grid">
            <Field label="Match in"><Select value={form.field} onChange={(e) => setForm({ ...form, field: e.target.value })} options={FIELDS.map(([value, label]) => ({ value, label }))} /></Field>
            <Field label="How"><Select value={form.match_type} onChange={(e) => setForm({ ...form, match_type: e.target.value })} options={MATCH.map(([value, label]) => ({ value, label }))} /></Field>
            <Field label="Pattern" required className="full"><input className="input" required value={form.pattern} placeholder={form.match_type === 'regex' ? '^UPI/.*/ZEPTO' : 'e.g. zepto'} onChange={(e) => setForm({ ...form, pattern: e.target.value })} /></Field>
            <Field label="Min amount"><input className="input" inputMode="decimal" value={form.amount_min} onChange={(e) => setForm({ ...form, amount_min: e.target.value })} /></Field>
            <Field label="Max amount"><input className="input" inputMode="decimal" value={form.amount_max} onChange={(e) => setForm({ ...form, amount_max: e.target.value })} /></Field>
            <Field label="Only for account"><Select value={form.account_id || ''} onChange={(e) => setForm({ ...form, account_id: e.target.value })} placeholder="Any account" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
            <Field label="Only for type"><Select value={form.transaction_type || ''} onChange={(e) => setForm({ ...form, transaction_type: e.target.value })} placeholder="Any type" options={['expense', 'income', 'refund', 'investment'].map((v) => ({ value: v, label: v }))} /></Field>
            <Field label="Set category"><Select value={form.set_category_id || ''} onChange={(e) => setForm({ ...form, set_category_id: e.target.value })} placeholder="—" options={[...categoryOptions(categories, 'expense'), ...categoryOptions(categories, 'income')]} /></Field>
            <Field label="Set merchant name"><input className="input" value={form.set_merchant_name || ''} onChange={(e) => setForm({ ...form, set_merchant_name: e.target.value })} /></Field>
            <Field label="Add tags" hint="Comma separated"><input className="input" value={form.add_tags} onChange={(e) => setForm({ ...form, add_tags: e.target.value })} /></Field>
            <Field label="Priority" hint="Lower runs first"><input className="input" type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></Field>
            <label className="checkbox"><input type="checkbox" checked={form.mark_reviewed} onChange={(e) => setForm({ ...form, mark_reviewed: e.target.checked })} />Mark as reviewed</label>
            <label className="checkbox"><input type="checkbox" checked={form.case_sensitive} onChange={(e) => setForm({ ...form, case_sensitive: e.target.checked })} />Case sensitive</label>
          </div>
          <FormError error={error} />
          <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save rule</Button></div>
        </form>
      </Modal>
      <Modal open={!!preview} onClose={() => setPreview(null)} title={`${preview?.count ?? 0} matching transactions`} wide>
        <div className="list">{preview?.sample?.map((t) => <div key={t.id} className="list-row"><span className="faint">{shortDate(t.date)}</span><span className="grow truncate">{t.description}</span><Money minor={t.amount_minor} currency={t.currency} /></div>)}</div>
      </Modal>
    </>
  )
}

function ruleBody(r, patch) {
  return {
    name: r.name, priority: r.priority, field: r.field, match_type: r.match_type, pattern: r.pattern, case_sensitive: r.case_sensitive,
    amount_min: r.amount_min_minor != null ? toInput(r.amount_min_minor) : null, amount_max: r.amount_max_minor != null ? toInput(r.amount_max_minor) : null,
    account_id: r.account_id, transaction_type: r.transaction_type, set_category_id: r.set_category_id, set_merchant_name: r.set_merchant_name,
    add_tags: [], mark_reviewed: r.mark_reviewed, enabled: r.enabled, ...patch,
  }
}

function Merchants() {
  const session = useSession()
  const { data: categories = [] } = useCategories()
  const [q, setQ] = useState('')
  const merchants = useQuery({ queryKey: ['merchants', q], queryFn: () => api.get('/merchants', { q }) })
  const update = useLedgerMutation(({ id, body }) => api.patch(`/merchants/${id}`, body))
  return (
    <Card>
      <div className="toolbar"><input className="input" placeholder="Search merchants" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search merchants" /></div>
      {merchants.isLoading ? <Loading /> : !merchants.data?.length ? <Empty icon={Shapes} title="No merchants yet">Merchants are created from transactions automatically.</Empty> : (
        <div className="table-wrap"><table className="table">
          <thead><tr><th>Merchant</th><th>Default category</th><th className="amount">Spent</th><th className="hide-mobile">Transactions</th><th className="hide-mobile">Last seen</th></tr></thead>
          <tbody>
            {merchants.data.map((m) => (
              <tr key={m.id}>
                <td><Link to={`/transactions?merchant_id=${m.id}`} style={{ color: 'var(--text)', fontWeight: 600 }}>{m.name}</Link></td>
                <td><Select value={m.default_category_id ? String(m.default_category_id) : ''} onChange={(e) => update.mutate({ id: m.id, body: { default_category_id: e.target.value ? Number(e.target.value) : null } })} placeholder="—" options={categoryOptions(categories, 'expense')} aria-label={`Default category for ${m.name}`} /></td>
                <td className="amount">{money(m.total_spent, session.settings.base_currency)}</td>
                <td className="hide-mobile">{m.transaction_count}</td>
                <td className="hide-mobile faint">{m.last_seen ? shortDate(m.last_seen) : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
      )}
    </Card>
  )
}
