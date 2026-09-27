import { useQuery } from '@tanstack/react-query'
import { BellRing, BrainCircuit, Copy, Download, KeyRound, Mail, Monitor, RefreshCw, Sparkles, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Badge, Button, Card, Field, FormError, Modal, PageHead, Segmented, Select, Switch } from '../components/ui'
import { api } from '../lib/api'
import { relativeTime, todayISO } from '../lib/format'
import { useSearchParams } from 'react-router-dom'
import { useAccounts, useLedgerMutation, useSession, useToast } from '../lib/hooks'
import { currentSubscription, disablePush, enablePush, pushSupport } from '../lib/push'

const SECTIONS = [
  { value: 'general', label: 'General' }, { value: 'notifications', label: 'Notifications' }, { value: 'fx', label: 'Exchange rates' },
  { value: 'ai', label: 'AI' }, { value: 'data', label: 'Data' }, { value: 'security', label: 'Security' }, { value: 'integrations', label: 'Integrations' }, { value: 'system', label: 'System' },
]
const CHANNELS = [['in_app', 'In-app'], ['email', 'Email'], ['sms', 'SMS'], ['whatsapp', 'WhatsApp'], ['push', 'Push']]
const CATEGORIES = [['budget', 'Budgets'], ['spending', 'Spending'], ['transaction', 'Transactions'], ['account', 'Accounts'], ['bills', 'Bills'], ['subscriptions', 'Subscriptions'], ['goals', 'Goals'], ['income', 'Income'], ['system', 'Bank sync & system']]

export default function Settings() {
  const [params, setParams] = useSearchParams()
  const section = params.get('section') || 'general'
  const setSection = (value) => setParams({ section: value }, { replace: true })
  return (
    <>
      <PageHead kicker="Workspace" title="Settings" />
      <div style={{ marginBottom: 16 }}><Segmented label="Settings section" value={section} onChange={setSection} options={SECTIONS} /></div>
      {section === 'general' && <General />}
      {section === 'notifications' && <Notifications />}
      {section === 'fx' && <ExchangeRates />}
      {section === 'ai' && <AISettings />}
      {section === 'data' && <Data />}
      {section === 'security' && <Security />}
      {section === 'integrations' && <Integrations />}
      {section === 'system' && <System />}
    </>
  )
}

function useSettingsSave() {
  const session = useSession()
  const toast = useToast()
  return useLedgerMutation((patch) => api.patch('/settings', patch), { onSuccess: () => { session.refresh(); toast.success('Settings saved') } })
}

function General() {
  const session = useSession()
  const s = session.settings
  const { data: accounts = [] } = useAccounts()
  const save = useSettingsSave()
  const [form, setForm] = useState({ display_name: session.user.display_name, timezone: s.timezone, week_start: s.week_start, default_account_id: s.default_account_id || '' })
  return (
    <div className="grid grid-2">
      <Card title="Profile & financial">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); save.mutate({ ...form, week_start: Number(form.week_start), default_account_id: form.default_account_id ? Number(form.default_account_id) : null }) }}>
          <Field label="Display name"><input className="input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>
          <Field label="Base currency" hint="Fixed once transactions exist – stored conversions depend on it."><input className="input" value={s.base_currency} disabled /></Field>
          <Field label="Time zone" hint="Decides what 'today' and 'this month' mean"><input className="input" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></Field>
          <Field label="Week starts on"><Select value={String(form.week_start)} onChange={(e) => setForm({ ...form, week_start: e.target.value })} options={['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'].map((d, i) => ({ value: String(i), label: d }))} /></Field>
          <Field label="Default account" hint="Pre-selected in quick add and used by the SMS webhook"><Select value={String(form.default_account_id || '')} onChange={(e) => setForm({ ...form, default_account_id: e.target.value })} placeholder="None" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
          <div><Button type="submit" variant="primary" loading={save.isPending}>Save</Button></div>
        </form>
      </Card>
      <Card title="Appearance">
        <div className="stack">
          <Field label="Theme"><Segmented label="Theme" value={s.theme} onChange={(theme) => save.mutate({ theme })} options={[{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }, { value: 'system', label: 'System' }]} /></Field>
          <div className="row between"><div><strong>Reduce motion</strong><div className="faint" style={{ fontSize: 13 }}>Disables animations and the 3D hero. Your OS setting is always respected too.</div></div><Switch checked={s.reduce_motion} label="Reduce motion" onChange={(v) => save.mutate({ reduce_motion: v })} /></div>
          <div className="row between"><div><strong>Show setup checklist</strong><div className="faint" style={{ fontSize: 13 }}>On the dashboard until all steps are done</div></div><Switch checked={!s.onboarding_dismissed} label="Show setup checklist" onChange={(v) => save.mutate({ onboarding_dismissed: !v })} /></div>
        </div>
      </Card>
    </div>
  )
}

function Notifications() {
  const session = useSession()
  const s = session.settings
  const save = useSettingsSave()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api.get('/health') })
  const [contact, setContact] = useState({ contact_email: s.contact_email, contact_phone: s.contact_phone, whatsapp_number: s.whatsapp_number })
  const [matrix, setMatrix] = useState(s.notification_matrix)
  useEffect(() => setMatrix(s.notification_matrix), [s.notification_matrix])
  const notes = {
    email: health.data?.email?.startsWith('smtp') ? 'SMTP configured' : 'SMTP not configured – emails are written to the server log only',
    sms: 'Mock adapter – no SMS is sent (see docs/costs.md)',
    whatsapp: 'Mock adapter – no message is sent (see docs/costs.md)',
    push: 'Browser notifications via Web Push – free, enable per device below',
    in_app: 'Always free',
  }
  return (
    <div className="stack" style={{ gap: 16 }}>
      <Card title="Channels" sub="Master switches – a channel that is off here is never used">
        <div className="list">
          {CHANNELS.map(([key, label]) => (
            <div key={key} className="list-row">
              <div className="grow"><strong>{label}</strong><div className="faint" style={{ fontSize: 13 }}>{notes[key]}</div></div>
              {['sms', 'whatsapp'].includes(key) && <Badge tone="warning">mock</Badge>}
              <Switch checked={s.channels[key]} label={label} onChange={(v) => save.mutate({ channels: { [key]: v } })} />
            </div>
          ))}
        </div>
      </Card>
      <DeliveryTests />
      <Card title="Where to send">
        <form className="form-grid" onSubmit={(e) => { e.preventDefault(); save.mutate(contact) }}>
          <Field label="Email"><input className="input" type="email" value={contact.contact_email} onChange={(e) => setContact({ ...contact, contact_email: e.target.value })} /></Field>
          <Field label="Mobile (SMS)" hint="E.164, e.g. +919876543210"><input className="input" value={contact.contact_phone} onChange={(e) => setContact({ ...contact, contact_phone: e.target.value })} /></Field>
          <Field label="WhatsApp number"><input className="input" value={contact.whatsapp_number} onChange={(e) => setContact({ ...contact, whatsapp_number: e.target.value })} /></Field>
          <div className="full"><Button type="submit" variant="primary" loading={save.isPending}>Save contacts</Button></div>
        </form>
      </Card>
      <Card title="Defaults per alert type" sub="Used by rules set to 'use my defaults'. Individual rules can override this.">
        <div className="table-wrap">
          <table className="matrix">
            <thead><tr><th>Alert type</th>{CHANNELS.map(([k, l]) => <th key={k}>{l}</th>)}</tr></thead>
            <tbody>{CATEGORIES.map(([cat, label]) => (
              <tr key={cat}><td>{label}</td>{CHANNELS.map(([ch]) => (
                <td key={ch}><input type="checkbox" aria-label={`${label} via ${ch}`} checked={!!matrix?.[cat]?.[ch]} onChange={(e) => setMatrix({ ...matrix, [cat]: { ...(matrix[cat] || {}), [ch]: e.target.checked } })} /></td>
              ))}</tr>
            ))}</tbody>
          </table>
        </div>
        <div style={{ marginTop: 12 }}><Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ notification_matrix: matrix })}>Save defaults</Button></div>
      </Card>
    </div>
  )
}

function ExchangeRates() {
  const session = useSession()
  const toast = useToast()
  const rates = useQuery({ queryKey: ['fx'], queryFn: () => api.get('/exchange-rates') })
  const [form, setForm] = useState({ base_currency: 'USD', quote_currency: session.settings.base_currency, rate: '', as_of: todayISO() })
  const [error, setError] = useState(null)
  const add = useLedgerMutation((b) => api.post('/exchange-rates', b), { onSuccess: () => { toast.success('Rate saved'); setForm({ ...form, rate: '' }) }, onError: setError })
  const remove = useLedgerMutation((id) => api.delete(`/exchange-rates/${id}`))
  return (
    <div className="grid grid-2">
      <Card title="Add a rate" sub="Rates are entered manually – no paid FX API. The latest rate on or before a date is used.">
        <form className="form-grid" onSubmit={(e) => { e.preventDefault(); setError(null); add.mutate(form) }}>
          <Field label="1 unit of"><Select value={form.base_currency} onChange={(e) => setForm({ ...form, base_currency: e.target.value })} options={['USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD', 'INR'].map((c) => ({ value: c, label: c }))} /></Field>
          <Field label="equals (currency)"><Select value={form.quote_currency} onChange={(e) => setForm({ ...form, quote_currency: e.target.value })} options={['INR', 'USD', 'EUR', 'GBP'].map((c) => ({ value: c, label: c }))} /></Field>
          <Field label="Rate" required><input className="input" required inputMode="decimal" value={form.rate} placeholder="e.g. 83.45" onChange={(e) => setForm({ ...form, rate: e.target.value })} /></Field>
          <Field label="As of"><input className="input" type="date" value={form.as_of} onChange={(e) => setForm({ ...form, as_of: e.target.value })} /></Field>
          <FormError error={error} />
          <div className="full"><Button type="submit" variant="primary" loading={add.isPending}>Save rate</Button></div>
        </form>
      </Card>
      <Card title="Saved rates">
        {!rates.data?.length ? <p className="muted">No rates yet. Only needed for accounts in another currency.</p> : (
          <div className="list">{rates.data.map((r) => <div key={r.id} className="list-row"><span className="grow num">1 {r.base_currency} = {Number(r.rate)} {r.quote_currency}</span><span className="faint">{r.as_of}</span><Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete rate" onClick={() => remove.mutate(r.id)} /></div>)}</div>
        )}
      </Card>
    </div>
  )
}

function Data() {
  const toast = useToast()
  const fileRef = useRef(null)
  const [pending, setPending] = useState(null)
  const restore = useLedgerMutation((file) => { const form = new FormData(); form.append('file', file); return api.upload('/backup/restore', form, { confirm: true }) }, {
    onSuccess: (r) => { toast.success(`Restored ${r.transactions} transactions (${r.format} backup)`); setPending(null) }, onError: (e) => { toast.error(e.message); setPending(null) },
  })
  return (
    <div className="grid grid-2">
      <Card title="Backup" sub="A portable JSON file with every account, transaction, budget, goal, bill, subscription and rule">
        <div className="stack">
          <Button icon={Download} onClick={() => api.download('/backup', null, 'hisaab-backup.json').catch((e) => toast.error(e.message))}>Download backup</Button>
          <Button icon={Upload} onClick={() => fileRef.current?.click()}>Restore from backup…</Button>
          <input ref={fileRef} type="file" hidden accept="application/json,.json" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) setPending(f) }} />
          <p className="faint" style={{ fontSize: 13, margin: 0 }}>Also accepts backups from the previous version (Ledgerly). Keep backups outside OneDrive/Git if they contain sensitive data.</p>
        </div>
      </Card>
      <Card title="Export" sub="Spreadsheets for your own analysis">
        <div className="stack">
          <Button icon={Download} onClick={() => api.download('/reports/transactions', { preset: 'custom', start: '1970-01-01', end: todayISO(), format: 'csv' }, 'transactions.csv').catch((e) => toast.error(e.message))}>All transactions (CSV)</Button>
          <Button icon={Download} onClick={() => api.download('/reports/transactions', { preset: 'custom', start: '1970-01-01', end: todayISO(), format: 'xlsx' }, 'transactions.xlsx').catch((e) => toast.error(e.message))}>All transactions (Excel)</Button>
          <p className="faint" style={{ fontSize: 13, margin: 0 }}>More reports (budgets, cash flow, net worth) on the Reports page.</p>
        </div>
      </Card>
      <Modal open={!!pending} onClose={() => setPending(null)} title="Replace all data?" footer={<><Button onClick={() => setPending(null)}>Cancel</Button><Button variant="danger solid" loading={restore.isPending} onClick={() => restore.mutate(pending)}>Restore and replace</Button></>}>
        <p className="muted" style={{ margin: 0 }}>Restoring <strong>{pending?.name}</strong> deletes the accounts, transactions, budgets, goals, bills, subscriptions and rules currently in this workspace. Download a backup first if unsure.</p>
      </Modal>
    </div>
  )
}

function Security() {
  const session = useSession()
  const toast = useToast()
  const sessions = useQuery({ queryKey: ['sessions'], queryFn: () => api.get('/auth/sessions') })
  const audit = useQuery({ queryKey: ['audit'], queryFn: () => api.get('/audit-log', { limit: 50 }) })
  const [pw, setPw] = useState({ current_password: '', new_password: '' })
  const [error, setError] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [confirmPw, setConfirmPw] = useState('')
  const change = useLedgerMutation((b) => api.post('/auth/change-password', b), { onSuccess: () => { toast.success('Password changed · other sessions signed out'); setPw({ current_password: '', new_password: '' }) }, onError: setError })
  const revoke = useLedgerMutation((id) => api.delete(`/auth/sessions/${id}`))
  const del = useLedgerMutation(() => api.post('/me/delete', { password: confirmPw }), { onSuccess: () => window.location.reload(), onError: (e) => toast.error(e.message) })
  return (
    <div className="grid grid-2">
      {!session.user.is_demo && (
        <Card title="Change password">
          <form className="stack" onSubmit={(e) => { e.preventDefault(); setError(null); change.mutate(pw) }}>
            <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field>
            <Field label="New password" hint="10+ characters, upper & lower case and a number"><input className="input" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field>
            <FormError error={error} />
            <div><Button type="submit" variant="primary" icon={KeyRound} loading={change.isPending}>Change password</Button></div>
          </form>
        </Card>
      )}
      <Card title="Active sessions">
        <div className="list">{sessions.data?.map((x) => (
          <div key={x.id} className="list-row"><Monitor size={16} className="faint" /><div className="grow"><div className="truncate" style={{ fontSize: 13 }}>{x.user_agent || 'Unknown device'}</div><div className="faint" style={{ fontSize: 12 }}>{x.ip_address} · active {relativeTime(x.last_seen_at)}</div></div>{x.current ? <Badge tone="success">this device</Badge> : <Button size="sm" onClick={() => revoke.mutate(x.id)}>Sign out</Button>}</div>
        ))}</div>
      </Card>
      <Card title="Audit log" sub="Security-relevant actions. Secrets are never logged." className="span-2">
        <div className="table-wrap"><table className="table">
          <thead><tr><th>When</th><th>Action</th><th className="hide-mobile">Details</th><th className="hide-mobile">IP</th></tr></thead>
          <tbody>{audit.data?.map((a) => <tr key={a.id}><td className="faint" style={{ whiteSpace: 'nowrap' }}>{relativeTime(a.created_at)}</td><td><code>{a.action}</code></td><td className="hide-mobile faint" style={{ fontSize: 12 }}>{Object.entries(a.details || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join(' · ')}</td><td className="hide-mobile faint">{a.ip_address}</td></tr>)}</tbody>
        </table></div>
      </Card>
      <Card title="Delete account" className="span-2">
        <p className="muted" style={{ marginTop: 0 }}>Permanently deletes this user and every record belonging to it. Download a backup first.</p>
        <Button variant="danger" icon={Trash2} onClick={() => setDeleting(true)}>Delete my account…</Button>
      </Card>
      <Modal open={deleting} onClose={() => setDeleting(false)} title="Delete everything?" footer={<><Button onClick={() => setDeleting(false)}>Cancel</Button><Button variant="danger solid" loading={del.isPending} onClick={() => del.mutate()}>Delete permanently</Button></>}>
        {!session.user.is_demo && <Field label="Confirm with your password"><input className="input" type="password" value={confirmPw} onChange={(e) => setConfirmPw(e.target.value)} /></Field>}
      </Modal>
    </div>
  )
}

function Integrations() {
  const session = useSession()
  const toast = useToast()
  const [token, setToken] = useState(null)
  const rotate = useLedgerMutation(() => api.post('/settings/sms-webhook-token'), { onSuccess: (r) => { setToken(r.token); session.refresh() } })
  const revoke = useLedgerMutation(() => api.delete('/settings/sms-webhook-token'), { onSuccess: () => { setToken(null); session.refresh(); toast.success('Token revoked') } })
  return (
    <div className="grid grid-2">
      <Card title="SMS webhook" sub="Lets an SMS-forwarder app on your phone post bank SMS to the app">
        <div className="stack">
          <div>Status: {session.settings.sms_webhook_configured ? <Badge tone="success">active · ends in {session.settings.sms_webhook_token_hint}</Badge> : <Badge>not set up</Badge>}</div>
          {token && (
            <div className="notice warning"><div className="grow"><strong>Copy this token now – it won't be shown again</strong><code style={{ wordBreak: 'break-all' }}>{token}</code></div><Button size="sm" icon={Copy} onClick={() => { navigator.clipboard.writeText(token); toast.success('Copied') }}>Copy</Button></div>
          )}
          <div className="row"><Button variant="primary" loading={rotate.isPending} onClick={() => rotate.mutate()}>{session.settings.sms_webhook_configured ? 'Rotate token' : 'Create token'}</Button>{session.settings.sms_webhook_configured && <Button variant="danger" onClick={() => revoke.mutate()}>Revoke</Button>}</div>
          <p className="faint" style={{ fontSize: 13, margin: 0 }}>Endpoint: <code>POST /api/sms/webhook</code> with <code>Authorization: Bearer &lt;token&gt;</code> and body <code>{'{"text": "…"}'}</code>. Requires a default account (General).</p>
        </div>
      </Card>
      <Card title="Optional AI assistant" sub="Not enabled">
        <p className="muted" style={{ marginTop: 0 }}>The core app needs no AI. A future assistant could answer questions like “where did I spend most this month?” using a local model through Ollama (free, runs on your machine) or an optional cloud provider. See docs/architecture.md → Roadmap.</p>
      </Card>
    </div>
  )
}

function System() {
  const health = useQuery({ queryKey: ['health'], queryFn: () => api.get('/health'), refetchInterval: 20_000 })
  const jobs = useQuery({ queryKey: ['jobs'], queryFn: () => api.get('/jobs') })
  const h = health.data
  return (
    <div className="grid grid-2">
      <Card title="Services">
        {h && (
          <div className="list">
            <div className="list-row"><span className="grow">Database</span><Badge tone={h.database.status === 'ok' ? 'success' : 'critical'}>{h.database.engine} · {h.database.status}</Badge></div>
            <div className="list-row"><span className="grow">Background worker</span><Badge tone={h.worker?.running ? 'success' : 'warning'}>{h.worker?.running ? `running · ${h.worker.seconds_ago}s ago` : 'not running'}</Badge></div>
            <div className="list-row"><span className="grow">Queued jobs</span><Badge>{h.jobs_queued}</Badge></div>
            <div className="list-row"><span className="grow">Email</span><Badge tone={h.email.startsWith('smtp') ? 'success' : 'warning'}>{h.email}</Badge></div>
            <div className="list-row"><span className="grow">SMS</span><Badge tone="warning">{h.sms}</Badge></div>
            <div className="list-row"><span className="grow">WhatsApp</span><Badge tone="warning">{h.whatsapp}</Badge></div>
          </div>
        )}
        {!h?.worker?.running && <p className="faint" style={{ fontSize: 13 }}>Start the worker with <code>python -m app.worker</code> (or <code>scripts/dev.ps1</code>) so date-based alerts, recurring transactions, email delivery and auto-sync run on schedule.</p>}
      </Card>
      <Card title="Recent jobs">
        {!jobs.data?.jobs?.length ? <p className="muted">No jobs in the last 3 days.</p> : (
          <div className="list">{jobs.data.jobs.map((j) => <div key={j.id} className="list-row"><code>{j.type}</code><span className="grow faint" style={{ fontSize: 12 }}>{relativeTime(j.created_at)}{j.last_error ? ` · ${j.last_error}` : ''}</span><Badge tone={j.status === 'done' ? 'success' : j.status === 'failed' ? 'critical' : 'accent'}>{j.status}</Badge></div>)}</div>
        )}
      </Card>
    </div>
  )
}


function DeliveryTests() {
  const session = useSession()
  const toast = useToast()
  const health = useQuery({ queryKey: ['health'], queryFn: () => api.get('/health') })
  const devices = useQuery({ queryKey: ['push-devices'], queryFn: () => api.get('/push/devices') })
  const [subscribed, setSubscribed] = useState(null)
  const [busy, setBusy] = useState('')
  const support = pushSupport()
  useEffect(() => {
    if (support.supported) currentSubscription().then((sub) => setSubscribed(!!sub)).catch(() => setSubscribed(false))
  }, [support.supported])
  const run = async (key, fn) => {
    setBusy(key)
    try { await fn() } catch (e) { toast.error(e.message) } finally { setBusy('') }
  }
  const emailOk = health.data?.email?.startsWith('smtp')
  return (
    <div className="grid grid-2">
      <Card title="Email" sub={emailOk ? 'SMTP is configured' : 'SMTP not configured yet'} action={<Mail size={16} className="faint" />}>
        {!emailOk && (
          <div className="notice warning" style={{ marginBottom: 12 }}><div>
            <strong>Add your SMTP details to backend/.env</strong>
            Replace the dummy values (Gmail: <code>SMTP_HOST=smtp.gmail.com</code>, <code>SMTP_PORT=587</code>, your address and a 16-character App Password), then restart the API and worker.
          </div></div>
        )}
        <Button icon={Mail} loading={busy === 'email'} onClick={() => run('email', async () => {
          const r = await api.post('/notifications/test-email')
          if (r.status === 'sent') toast.success(`Test email sent to ${r.to}`)
          else toast.error(r.error || `Email ${r.status}`)
        })}>Send test email</Button>
        <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>Sent to {session.settings.contact_email || session.user.email}.</p>
      </Card>
      <Card title="Push on this device" sub={support.supported ? `Browser permission: ${Notification.permission}` : support.reason} action={<BellRing size={16} className="faint" />}>
        <div className="row wrap">
          {subscribed ? (
            <>
              <Button variant="primary" icon={BellRing} loading={busy === 'push-test'} onClick={() => run('push-test', async () => { await api.post('/push/test'); toast.success('Push sent – check your notifications') })}>Send test push</Button>
              <Button loading={busy === 'push-off'} onClick={() => run('push-off', async () => { await disablePush(); setSubscribed(false); session.refresh(); devices.refetch() })}>Turn off here</Button>
            </>
          ) : (
            <Button variant="primary" icon={BellRing} disabled={!support.supported} loading={busy === 'push-on'} onClick={() => run('push-on', async () => {
              await enablePush()
              setSubscribed(true)
              session.refresh()
              devices.refetch()
              toast.success('Push notifications enabled on this device')
            })}>Enable push notifications</Button>
          )}
        </div>
        <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>{devices.data?.length || 0} device(s) subscribed. Works on localhost; other addresses need HTTPS.</p>
      </Card>
    </div>
  )
}

function AISettings() {
  const toast = useToast()
  const status = useQuery({ queryKey: ['ai-status'], queryFn: () => api.get('/ai/status') })
  const train = useLedgerMutation(() => api.post('/ai/train'), { onSuccess: () => { toast.success('Model retrained'); status.refetch() } })
  const categorize = useLedgerMutation((scope) => api.post('/ai/categorize', { scope }), {
    onSuccess: (r) => toast.success(`${r.categorized_by_ml} by ML, ${r.categorized_by_llm} by local AI · ${r.still_uncertain} still need you`),
  })
  const ml = status.data?.ml
  const llm = status.data?.llm
  return (
    <div className="grid grid-2">
      <Card title="Smart categorisation (ML)" sub="scikit-learn · runs on this computer · free" action={<BrainCircuit size={16} className="faint" />}>
        {ml && (
          <div className="stack" style={{ gap: 8, fontSize: 14 }}>
            <div className="row between"><span className="muted">Status</span><Badge tone={ml.trained ? 'success' : 'warning'}>{ml.trained ? 'trained' : 'not trained yet'}</Badge></div>
            {ml.trained && (
              <>
                <div className="row between"><span className="muted">Your labelled examples</span><strong>{ml.user_samples}</strong></div>
                <div className="row between"><span className="muted">Categories learned</span><strong>{ml.classes}</strong></div>
                <div className="row between"><span className="muted">Accuracy on your recent data</span><strong>{ml.holdout_accuracy != null ? `${Math.round(ml.holdout_accuracy * 100)}%` : 'needs 40+ examples'}</strong></div>
                <div className="row between"><span className="muted">Last trained</span><span>{relativeTime(ml.trained_at)}</span></div>
              </>
            )}
            <p className="faint" style={{ fontSize: 12, margin: '6px 0' }}>Every time you pick or correct a category, the model gets better. It retrains automatically in the background worker.</p>
            <div className="row wrap">
              <Button icon={RefreshCw} loading={train.isPending} onClick={() => train.mutate()}>Retrain now</Button>
              <Button variant="primary" icon={Sparkles} loading={categorize.isPending} onClick={() => categorize.mutate('uncategorized')}>Categorise uncategorised</Button>
            </div>
          </div>
        )}
      </Card>
      <Card title="Local AI model (optional)" sub="Open-source LLM through Ollama – free, private" action={<Sparkles size={16} className="faint" />}>
        {llm && (llm.available ? (
          <div className="stack" style={{ gap: 8 }}>
            <div className="notice success"><div><strong>Connected: {llm.model}</strong>{llm.base_url}{!llm.local && ' – note: this server is not on your computer'}</div></div>
            <p className="faint" style={{ fontSize: 13, margin: 0 }}>Used for “Ask your money” and for transactions the ML model is unsure about.</p>
          </div>
        ) : (
          <div className="stack" style={{ gap: 10, fontSize: 14 }}>
            <div className="notice"><div><strong>Not connected</strong><span className="faint" style={{ fontSize: 12 }}>{llm.reason}</span></div></div>
            <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
              <li>Install <strong>Ollama</strong> (free, open source) from ollama.com – on a work laptop this may need IT approval.</li>
              <li>In a terminal: <code>ollama pull {llm.model || 'qwen2.5:3b'}</code> (about 2 GB, Apache-2.0 licence).</li>
              <li>Keep Ollama running, then click “Check again”.</li>
            </ol>
            <p className="faint" style={{ fontSize: 12, margin: 0 }}>Everything works without it – the rules engine answers questions and the ML model categorises.</p>
            <div><Button icon={RefreshCw} onClick={() => status.refetch()}>Check again</Button></div>
          </div>
        ))}
      </Card>
      <Card title="Reading statements" className="span-2">
        <div className="grid grid-3" style={{ fontSize: 14 }}>
          <div><strong>Entity extraction</strong><p className="muted" style={{ margin: '4px 0 0' }}>Pulls the mode (UPI/NEFT/IMPS/card…), UPI id, reference number, payee, bank and card digits out of every narration.</p></div>
          <div><strong>OCR</strong><p className="muted" style={{ margin: '4px 0 0' }}>Scanned PDFs and photos are read locally with RapidOCR (open source) – nothing is uploaded anywhere.</p></div>
          <div><strong>Balance check</strong><p className="muted" style={{ margin: '4px 0 0' }}>For PDFs and text statements, debit vs credit is confirmed from the running balance, not guessed.</p></div>
        </div>
      </Card>
    </div>
  )
}
