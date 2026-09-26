import { useQuery } from '@tanstack/react-query'
import { BellRing, FlaskConical, Pencil, Plus, Send, Sparkles, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Confirm, Empty, Field, FormError, Loading, Modal, PageHead, Segmented, Select, Switch } from '../components/ui'
import { api } from '../lib/api'
import { relativeTime } from '../lib/format'
import { useAccounts, useCategories, useLedgerMutation, useSession, useToast } from '../lib/hooks'

const OP_LABEL = { '>': 'is greater than', '>=': 'is at least', '<': 'is less than', '<=': 'is at most', '=': 'equals', '!=': 'is not' }
const POLICIES = [
  { value: 'once_per_threshold', label: 'Once per threshold / period' },
  { value: 'once_per_day', label: 'At most once a day' },
  { value: 'cooldown', label: 'Cooldown (minutes)' },
  { value: 'every_event', label: 'Every time' },
]
const CHANNELS = [['in_app', 'In-app'], ['email', 'Email'], ['sms', 'SMS'], ['whatsapp', 'WhatsApp'], ['push', 'Push']]
const DELIVERY_TONE = { sent: 'success', logged: 'warning', mocked: 'warning', queued: 'accent', failed: 'critical', skipped: '' }

const TEMPLATES = [
  { name: 'Food spending over ₹8,000 this month', metric: 'category_spending', params: { period: 'month' }, operator: '>', threshold: '8000', needs: 'category' },
  { name: 'Balance below ₹10,000', metric: 'account_balance', operator: '<', threshold: '10000' },
  { name: 'Single payment over ₹5,000', metric: 'large_transaction', operator: '>', threshold: '5000', cooldown_policy: 'every_event' },
  { name: 'Weekly spending over ₹15,000', metric: 'total_spending', params: { period: 'week' }, operator: '>', threshold: '15000' },
  { name: 'Unusual transaction (3× typical)', metric: 'unusual_transaction', operator: '>=', threshold: '3', cooldown_policy: 'every_event' },
  { name: 'New merchant', metric: 'new_merchant', cooldown_policy: 'every_event' },
  { name: 'Refund received', metric: 'refund_received', operator: '>', threshold: '0', cooldown_policy: 'every_event' },
  { name: 'Salary received', metric: 'salary_detected', operator: '>', threshold: '0', cooldown_policy: 'every_event' },
  { name: 'Savings rate below 20%', metric: 'savings_rate', operator: '<', threshold: '20' },
  { name: 'Goal behind schedule', metric: 'goal_behind_schedule', operator: '>', threshold: '10' },
  { name: 'Goal 50% milestone', metric: 'goal_progress', operator: '>=', threshold: '50' },
  { name: 'Subscription price changed', metric: 'subscription_price_changed', cooldown_policy: 'every_event' },
]

export default function Alerts() {
  const [params, setParams] = useSearchParams()
  const [tab, setTab] = useState(params.get('tab') || 'rules')
  return (
    <>
      <PageHead kicker="Automation" title="Alerts">
        WHEN a metric crosses a threshold THEN notify you. Rules are checked after every change and by the background worker, so alerts don't need a browser tab open.
      </PageHead>
      <div style={{ marginBottom: 16 }}><Segmented label="Section" value={tab} onChange={(t) => { setTab(t); setParams({ tab: t }, { replace: true }) }} options={[{ value: 'rules', label: 'Rules' }, { value: 'history', label: 'History & delivery' }]} /></div>
      {tab === 'rules' ? <Rules openNew={params.get('new')} /> : <History />}
    </>
  )
}

function Rules({ openNew }) {
  const session = useSession()
  const toast = useToast()
  const metrics = useQuery({ queryKey: ['alert-metrics'], queryFn: () => api.get('/alerts/metrics'), staleTime: Infinity })
  const rules = useQuery({ queryKey: ['alert-rules'], queryFn: () => api.get('/alerts/rules') })
  const budgets = useQuery({ queryKey: ['budgets'], queryFn: () => api.get('/budgets') })
  const goals = useQuery({ queryKey: ['goals'], queryFn: () => api.get('/goals') })
  const { data: accounts = [] } = useAccounts()
  const { data: categories = [] } = useCategories()
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState(null)
  const [testResult, setTestResult] = useState(null)
  const [deleting, setDeleting] = useState(null)
  const byKey = useMemo(() => Object.fromEntries((metrics.data || []).map((m) => [m.key, m])), [metrics.data])

  const open = (rule, template) => {
    setError(null)
    setEditing(rule || 'new')
    const base = rule || template || { name: '', metric: 'budget_usage', params: {}, operator: '>=', threshold: '80' }
    setForm({ name: base.name || '', metric: base.metric, params: { ...(base.params || {}) }, operator: base.operator || byKey[base.metric]?.default_operator || '>=', threshold: base.threshold ?? byKey[base.metric]?.default_threshold ?? '', channels: base.channels ?? null, cooldown_policy: base.cooldown_policy || byKey[base.metric]?.default_policy || 'once_per_threshold', cooldown_minutes: base.cooldown_minutes || 60, enabled: base.enabled ?? true })
  }
  useEffect(() => { if (openNew && metrics.data) open(null) }, [openNew, metrics.data]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = useLedgerMutation((b) => (editing === 'new' ? api.post('/alerts/rules', b) : api.put(`/alerts/rules/${editing.id}`, b)), {
    onSuccess: (r) => { toast.success(r.fired_now?.length ? `Saved – already triggered: ${r.fired_now.join(', ')}` : 'Alert rule saved'); setEditing(null) }, onError: setError,
  })
  const toggle = useLedgerMutation((r) => api.put(`/alerts/rules/${r.id}`, { ...r, threshold: r.threshold, enabled: !r.enabled, last_triggered_at: undefined, last_evaluated_at: undefined, id: undefined }))
  const remove = useLedgerMutation((id) => api.delete(`/alerts/rules/${id}`), { onSuccess: () => { toast.success('Rule deleted'); setDeleting(null) } })
  const testChannels = useLedgerMutation(() => api.post('/alerts/test-notification'), { onSuccess: (r) => setTestResult({ title: 'Test notification', deliveries: r.deliveries }) })

  const metric = form && byKey[form.metric]
  const unit = metric?.unit
  const cur = session.settings.base_currency
  const describe = (r) => {
    const m = byKey[r.metric]
    if (!m) return r.metric
    if (m.boolean) return m.label
    const value = r.threshold == null ? '' : m.unit === 'money' ? `₹${Number(r.threshold).toLocaleString('en-IN')}` : m.unit === 'percent' ? `${Number(r.threshold)}%` : m.unit === 'days' ? `${Number(r.threshold)} days` : m.unit === 'multiplier' ? `${Number(r.threshold)}×` : r.threshold
    return `${m.label} ${OP_LABEL[r.operator] || r.operator} ${value}`
  }
  const paramLabel = (r) => {
    const p = r.params || {}
    const bits = []
    if (p.budget_id) bits.push(budgets.data?.find((b) => b.id === Number(p.budget_id))?.name)
    if (p.category_id) bits.push(categories.find((c) => c.id === Number(p.category_id))?.name)
    if (p.account_id) bits.push(accounts.find((a) => a.id === Number(p.account_id))?.name)
    if (p.goal_id) bits.push(goals.data?.find((g) => g.id === Number(p.goal_id))?.name)
    if (p.period) bits.push(`per ${p.period}`)
    return bits.filter(Boolean).join(' · ')
  }

  const submit = (e) => {
    e.preventDefault()
    setError(null)
    save.mutate({ ...form, threshold: metric?.boolean || form.threshold === '' ? null : String(form.threshold), cooldown_minutes: Number(form.cooldown_minutes) || 0 })
  }

  return (
    <>
      <div className="row wrap" style={{ marginBottom: 14 }}>
        <Button variant="primary" icon={Plus} onClick={() => open(null)}>New alert</Button>
        <Button icon={Send} loading={testChannels.isPending} onClick={() => testChannels.mutate()}>Send test notification</Button>
      </div>
      <Card title="Quick templates" sub="Start from a common alert and adjust" style={{ marginBottom: 16 }}>
        <div className="row wrap" style={{ gap: 8 }}>
          {TEMPLATES.map((t) => <Button key={t.name} size="sm" icon={Sparkles} onClick={() => open(null, t)}>{t.name}</Button>)}
        </div>
      </Card>
      <Card title="Your rules">
        {rules.isLoading || metrics.isLoading ? <Loading /> : !rules.data?.length ? <Empty icon={BellRing} title="No alert rules" /> : (
          <div className="list">
            {rules.data.map((r) => (
              <div key={r.id} className="list-row" style={{ opacity: r.enabled ? 1 : 0.55, flexWrap: 'wrap' }}>
                <span className="avatar"><BellRing size={16} /></span>
                <div className="grow" style={{ minWidth: 200 }}>
                  <div style={{ fontWeight: 700 }}>{r.name}</div>
                  <div className="faint" style={{ fontSize: 13 }}>
                    WHEN {describe(r)}{paramLabel(r) ? ` (${paramLabel(r)})` : ''} THEN {(r.channels || ['category defaults']).join(' + ')}
                    {' · '}{POLICIES.find((p) => p.value === r.cooldown_policy)?.label.toLowerCase()}
                    {r.last_triggered_at ? ` · last fired ${relativeTime(r.last_triggered_at)}` : ''}
                  </div>
                </div>
                <Badge>{byKey[r.metric]?.category}</Badge>
                <Switch checked={r.enabled} label={`Enable ${r.name}`} onChange={() => toggle.mutate(r)} />
                <Button size="sm" variant="ghost" icon={FlaskConical} aria-label="Test (dry run)" onClick={async () => setTestResult({ title: r.name, ...(await api.post(`/alerts/rules/${r.id}/test`)) })} />
                <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => open(r)} />
                <Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete" onClick={() => setDeleting(r)} />
              </div>
            ))}
          </div>
        )}
      </Card>

      <Modal open={!!editing && !!form} onClose={() => setEditing(null)} title={editing === 'new' ? 'New alert rule' : 'Edit alert rule'} wide>
        {form && metric && (
          <form className="stack" onSubmit={submit}>
            <Field label="Name" required><input className="input" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Shopping over ₹4,000 this month" /></Field>
            <div className="card" style={{ padding: 16, background: 'var(--surface-2)' }}>
              <div className="kicker" style={{ marginBottom: 10 }}>When</div>
              <div className="form-grid">
                <Field label="Metric" className="full">
                  <Select value={form.metric} onChange={(e) => { const m = byKey[e.target.value]; setForm({ ...form, metric: e.target.value, params: {}, operator: m.default_operator, threshold: m.default_threshold ?? '', cooldown_policy: m.default_policy }) }}
                    options={['budget', 'spending', 'transaction', 'account', 'bills', 'subscriptions', 'goals', 'income', 'system'].map((cat) => ({ group: cat[0].toUpperCase() + cat.slice(1), options: (metrics.data || []).filter((m) => m.category === cat).map((m) => ({ value: m.key, label: m.label })) }))} />
                  <span className="hint">{metric.description}</span>
                </Field>
                {metric.params.budget_id && <Field label="Budget"><Select value={form.params.budget_id || ''} onChange={(e) => setForm({ ...form, params: { ...form.params, budget_id: e.target.value ? Number(e.target.value) : null } })} placeholder="Any budget" options={(budgets.data || []).map((b) => ({ value: String(b.id), label: b.name }))} /></Field>}
                {metric.params.category_id && <Field label="Category" required={form.metric === 'category_spending'}><Select value={form.params.category_id || ''} onChange={(e) => setForm({ ...form, params: { ...form.params, category_id: e.target.value ? Number(e.target.value) : null } })} placeholder={form.metric === 'expected_income_missing' ? 'Any income' : 'Choose…'} options={categoryOptions(categories, form.metric === 'expected_income_missing' ? 'income' : 'expense')} /></Field>}
                {metric.params.account_id && <Field label="Account"><Select value={form.params.account_id || ''} onChange={(e) => setForm({ ...form, params: { ...form.params, account_id: e.target.value ? Number(e.target.value) : null } })} placeholder="Any cash/bank account" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>}
                {metric.params.goal_id && <Field label="Goal"><Select value={form.params.goal_id || ''} onChange={(e) => setForm({ ...form, params: { ...form.params, goal_id: e.target.value ? Number(e.target.value) : null } })} placeholder="Any goal" options={(goals.data || []).map((g) => ({ value: String(g.id), label: g.name }))} /></Field>}
                {metric.params.period && <Field label="Period"><Select value={form.params.period || 'month'} onChange={(e) => setForm({ ...form, params: { ...form.params, period: e.target.value } })} options={[{ value: 'day', label: 'Today' }, { value: 'week', label: 'This week' }, { value: 'month', label: 'This month' }]} /></Field>}
                {metric.params.day_of_month && <Field label="By day of month"><input className="input" type="number" min={1} max={28} value={form.params.day_of_month || 5} onChange={(e) => setForm({ ...form, params: { ...form.params, day_of_month: Number(e.target.value) } })} /></Field>}
                {!metric.boolean && <>
                  <Field label="Operator"><Select value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })} options={metric.operators.map((o) => ({ value: o, label: OP_LABEL[o] }))} /></Field>
                  <Field label={`Value${unit === 'money' ? ` (${cur})` : unit === 'percent' ? ' (%)' : unit === 'days' ? ' (days)' : unit === 'multiplier' ? ' (× typical)' : ''}`} required>
                    <input className="input" required inputMode="decimal" value={form.threshold ?? ''} onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
                  </Field>
                </>}
              </div>
            </div>
            <div className="card" style={{ padding: 16, background: 'var(--surface-2)' }}>
              <div className="kicker" style={{ marginBottom: 10 }}>Then notify</div>
              <label className="checkbox" style={{ marginBottom: 10 }}><input type="checkbox" checked={form.channels === null} onChange={(e) => setForm({ ...form, channels: e.target.checked ? null : ['in_app'] })} />Use my defaults for “{metric.category}” alerts (Settings → Notifications)</label>
              {form.channels !== null && (
                <div className="row wrap">
                  {CHANNELS.map(([key, label]) => (
                    <label key={key} className="checkbox"><input type="checkbox" checked={form.channels.includes(key)} onChange={(e) => setForm({ ...form, channels: e.target.checked ? [...form.channels, key] : form.channels.filter((c) => c !== key) })} />{label}{!session.settings.channels[key] && <span className="faint" style={{ fontSize: 11 }}>(off in settings)</span>}</label>
                  ))}
                </div>
              )}
              <div className="form-grid" style={{ marginTop: 12 }}>
                <Field label="Repeat"><Select value={form.cooldown_policy} onChange={(e) => setForm({ ...form, cooldown_policy: e.target.value })} options={POLICIES.filter((p) => metric.kind === 'event' || p.value !== 'every_event')} /></Field>
                {form.cooldown_policy === 'cooldown' && <Field label="Cooldown minutes"><input className="input" type="number" min={1} value={form.cooldown_minutes} onChange={(e) => setForm({ ...form, cooldown_minutes: e.target.value })} /></Field>}
              </div>
            </div>
            <FormError error={error} />
            <div className="modal-foot"><Button onClick={() => setEditing(null)}>Cancel</Button><Button type="submit" variant="primary" loading={save.isPending}>Save rule</Button></div>
          </form>
        )}
      </Modal>
      <Modal open={!!testResult} onClose={() => setTestResult(null)} title={testResult?.title} footer={<Button onClick={() => setTestResult(null)}>Close</Button>}>
        {testResult?.deliveries && <Deliveries deliveries={testResult.deliveries} />}
        {testResult?.kind === 'event' && <p className="muted">{testResult.message}</p>}
        {testResult?.kind === 'state' && (testResult.observations.length ? (
          <div className="list">{testResult.observations.map((o) => <div key={o.entity} className="list-row"><Badge tone={o.condition_met ? 'warning' : 'success'}>{o.condition_met ? 'would fire' : 'ok'}</Badge><span className="grow muted" style={{ fontSize: 13 }}>{o.message}</span></div>)}</div>
        ) : <p className="muted">Nothing to evaluate yet (no matching budgets, bills, accounts or goals).</p>)}
        {testResult?.kind === 'state' && <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>Dry run – no notification was sent. “Would fire” respects the rule's repeat policy, so an alert already sent this period won't repeat.</p>}
      </Modal>
      <Confirm open={!!deleting} onClose={() => setDeleting(null)} title={`Delete “${deleting?.name}”?`} message="Past alert history is kept." loading={remove.isPending} onConfirm={() => remove.mutate(deleting.id)} />
    </>
  )
}

function Deliveries({ deliveries }) {
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {deliveries.map((d) => (
        <span key={d.id} title={d.error || d.destination} className={`badge ${DELIVERY_TONE[d.status] || ''}`}>
          {d.channel.replace('_', '-')} · {d.status}{d.status === 'logged' ? ' (SMTP not set)' : d.status === 'mocked' ? ' (mock)' : ''}
        </span>
      ))}
    </div>
  )
}

function History() {
  const events = useQuery({ queryKey: ['alert-events'], queryFn: () => api.get('/alerts/events', { limit: 200 }) })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.get('/jobs') })
  const tone = { critical: 'critical', warning: 'warning', success: 'success', info: 'accent' }
  return (
    <div className="stack" style={{ gap: 16 }}>
      {jobs.data && !jobs.data.worker.running && (
        <div className="notice warning"><div><strong>Background worker is not running</strong>Email/SMS deliveries stay “queued” and date-based alerts (bills, renewals) are only checked when you use the app. Start it with <code>python -m app.worker</code>.</div></div>
      )}
      <Card title="Alert history" sub="Every time a rule fired, and what happened on each channel">
        {events.isLoading ? <Loading /> : !events.data?.length ? <Empty icon={BellRing} title="No alerts have fired yet" /> : (
          <div className="list">
            {events.data.map((e) => (
              <div key={e.id} className="list-row" style={{ alignItems: 'flex-start', flexWrap: 'wrap' }}>
                <div className="faint num" style={{ width: 120, fontSize: 12, paddingTop: 2 }}>{new Date(e.triggered_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</div>
                <div className="grow" style={{ minWidth: 220 }}>
                  <div className="row" style={{ gap: 8 }}><strong>{e.title}</strong><Badge tone={tone[e.severity]}>{e.category}</Badge></div>
                  <div className="muted" style={{ fontSize: 13, margin: '3px 0 6px' }}>{e.message}</div>
                  <Deliveries deliveries={e.deliveries} />
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
