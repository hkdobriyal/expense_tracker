import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, FileUp, MessageSquareText, Undo2, Upload } from 'lucide-react'
import { useRef, useState } from 'react'
import { Badge, Button, Card, Empty, Field, FormError, Loading, PageHead, Segmented, Select } from '../components/ui'
import { api } from '../lib/api'
import { TYPE_LABEL, relativeTime, todayISO } from '../lib/format'
import { useAccounts, useLedgerMutation, useSession, useToast } from '../lib/hooks'

const MAP_FIELDS = [
  ['date', 'Date', true], ['description', 'Description / narration', true], ['amount', 'Amount (signed or with Dr/Cr)'],
  ['debit', 'Debit / withdrawal'], ['credit', 'Credit / deposit'], ['direction', 'Dr/Cr column'], ['balance', 'Balance'], ['external_id', 'Reference no.'],
]
const SIGN_MODES = [{ value: 'debit_credit', label: 'Separate debit & credit columns' }, { value: 'signed', label: 'One amount column (negative = out)' }, { value: 'direction_column', label: 'Amount + Dr/Cr column' }]
const STATUS_TONE = { ok: 'success', duplicate: 'warning', error: 'critical', imported: 'accent' }

export default function Import() {
  const [tab, setTab] = useState('file')
  return (
    <>
      <PageHead kicker="Connect" title="Import">Bring in real transactions from bank statements or bank SMS. Duplicates are detected before anything is saved.</PageHead>
      <div style={{ marginBottom: 16 }}><Segmented label="Import type" value={tab} onChange={setTab} options={[{ value: 'file', label: 'Statement file' }, { value: 'sms', label: 'Bank SMS' }, { value: 'history', label: 'History' }]} /></div>
      {tab === 'file' && <StatementImport />}
      {tab === 'sms' && <SmsImport />}
      {tab === 'history' && <ImportHistory />}
    </>
  )
}

function StatementImport() {
  const toast = useToast()
  const { data: accounts = [] } = useAccounts()
  const fileRef = useRef(null)
  const [file, setFile] = useState(null)
  const [password, setPassword] = useState('')
  const [accountId, setAccountId] = useState('')
  const [job, setJob] = useState(null)
  const [mapping, setMapping] = useState(null)
  const [includeDup, setIncludeDup] = useState(new Set())
  const [overrides, setOverrides] = useState({})
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [drag, setDrag] = useState(false)

  const upload = useLedgerMutation(() => {
    const form = new FormData()
    form.append('file', file)
    if (password) form.append('password', password)
    if (accountId) form.append('account_id', accountId)
    return api.upload('/imports', form)
  }, { onSuccess: (j) => { setJob(j); setMapping(j.mapping); setResult(null) }, onError: setError })
  const validate = useLedgerMutation(() => api.post(`/imports/${job.id}/validate`, { account_id: Number(accountId), mapping }), { onSuccess: setJob, onError: setError })
  const commit = useLedgerMutation(() => api.post(`/imports/${job.id}/commit`, { include_duplicate_rows: [...includeDup], type_overrides: overrides }), {
    onSuccess: (r) => { setResult(r); setJob(r.job); toast.success(`${r.imported} transactions imported`) }, onError: setError,
  })
  const undo = useLedgerMutation(() => api.post(`/imports/${job.id}/undo`), { onSuccess: (r) => { toast.success(`Removed ${r.removed} transactions`); reset() } })

  const reset = () => { setFile(null); setJob(null); setMapping(null); setResult(null); setIncludeDup(new Set()); setOverrides({}); setError(null) }
  const pick = (f) => { reset(); setFile(f) }
  const rows = job?.rows || []
  const counts = job?.counts
  const account = accounts.find((a) => String(a.id) === accountId)
  const fixedLayout = job && ['ofx', 'qfx', 'pdf'].includes(job.file_format)

  return (
    <div className="stack" style={{ gap: 16 }}>
      <Card title="1 · Upload" sub="CSV, Excel (XLSX), OFX/QFX or a text-based PDF – up to 10 MB">
        <div className={`drop ${drag ? 'active' : ''}`} role="button" tabIndex={0} onClick={() => fileRef.current?.click()} onKeyDown={(e) => e.key === 'Enter' && fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files?.[0]) }}>
          <FileUp size={28} className="faint" />
          <div style={{ fontWeight: 700, marginTop: 8 }}>{file ? file.name : 'Drop a statement here or click to choose'}</div>
          <div className="faint" style={{ fontSize: 13 }}>HDFC, SBI, ICICI, Axis, Kotak and most other bank exports work. CSV/XLSX import most reliably.</div>
          <input ref={fileRef} type="file" hidden accept=".csv,.txt,.xlsx,.ofx,.qfx,.pdf" onChange={(e) => pick(e.target.files?.[0])} />
        </div>
        <div className="form-grid" style={{ marginTop: 14 }}>
          <Field label="Import into account" required><Select value={accountId} onChange={(e) => setAccountId(e.target.value)} placeholder="Choose…" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} /></Field>
          {file?.name.toLowerCase().endsWith('.pdf') && <Field label="PDF password" hint="Often PAN in capitals + date of birth. Used once, never stored."><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="off" /></Field>}
        </div>
        <FormError error={!job && error} />
        <div className="row" style={{ marginTop: 14 }}><Button variant="primary" icon={Upload} disabled={!file || !accountId} loading={upload.isPending} onClick={() => { setError(null); upload.mutate() }}>Read file</Button></div>
      </Card>

      {job && mapping && job.status !== 'completed' && (
        <Card title="2 · Map columns" sub={`${job.file_format.toUpperCase()} · ${job.total_rows} rows${job.bank_detected ? ` · detected ${job.bank_detected}` : ''}`}>
          {fixedLayout ? <p className="muted" style={{ marginTop: 0 }}>This format has a fixed layout – no mapping needed.</p> : (
            <>
              <div className="form-grid">
                <Field label="How are amounts shown?" className="full"><Select value={mapping.sign} onChange={(e) => setMapping({ ...mapping, sign: e.target.value })} options={SIGN_MODES} /></Field>
                {MAP_FIELDS.filter(([k]) => (mapping.sign === 'debit_credit' ? !['amount', 'direction'].includes(k) : mapping.sign === 'signed' ? !['debit', 'credit', 'direction'].includes(k) : !['debit', 'credit'].includes(k))).map(([key, label, req]) => (
                  <Field key={key} label={label} required={req}>
                    <Select value={mapping[key] ?? ''} onChange={(e) => setMapping({ ...mapping, [key]: e.target.value === '' ? null : Number(e.target.value) })} placeholder="— not in file —" options={job.headers.map((h, i) => ({ value: String(i), label: h }))} />
                  </Field>
                ))}
                <Field label="Date format" hint="Auto-detect prefers DD/MM (Indian statements)"><Select value={mapping.date_format || ''} onChange={(e) => setMapping({ ...mapping, date_format: e.target.value || null })} placeholder="Auto-detect" options={['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%b-%Y', '%Y-%m-%d', '%m/%d/%Y'].map((f) => ({ value: f, label: f.replaceAll('%', '') }))} /></Field>
                <label className="checkbox"><input type="checkbox" checked={!!mapping.invert} onChange={(e) => setMapping({ ...mapping, invert: e.target.checked })} />Flip signs (credit-card exports)</label>
              </div>
              <div className="table-wrap" style={{ marginTop: 14 }}>
                <table className="table mapping-table"><thead><tr>{job.headers.map((h) => <th key={h}>{h}</th>)}</tr></thead>
                  <tbody>{job.sample_rows.slice(0, 5).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className="truncate" style={{ maxWidth: 200 }}>{c}</td>)}</tr>)}</tbody></table>
              </div>
            </>
          )}
          <FormError error={job && error} />
          <div className="row" style={{ marginTop: 14 }}><Button variant="primary" loading={validate.isPending} disabled={!accountId} onClick={() => { setError(null); validate.mutate() }}>Validate & check duplicates</Button></div>
        </Card>
      )}

      {job && rows.length > 0 && (
        <Card title={job.status === 'completed' ? 'Imported' : '3 · Review & confirm'} sub={account ? `into ${account.name}` : ''}
          action={job.status === 'completed' ? <Button size="sm" icon={Undo2} loading={undo.isPending} onClick={() => undo.mutate()}>Undo import</Button> : null}>
          {result ? (
            <div className="notice success" style={{ marginBottom: 14 }}><CheckCircle2 size={18} /><div><strong>Import finished</strong>{result.imported} imported · {result.duplicates_skipped} duplicates skipped · {result.errors} errors. Imported rows are marked “to review”.</div></div>
          ) : (
            <div className="row wrap" style={{ marginBottom: 12, gap: 8 }}>
              <Badge tone="success">{counts.ok} new</Badge><Badge tone="warning">{counts.duplicates} duplicates</Badge><Badge tone="critical">{counts.errors} errors</Badge>
            </div>
          )}
          <div className="table-wrap" style={{ maxHeight: 460, overflowY: 'auto' }}>
            <table className="table">
              <thead><tr><th>Status</th><th>Date</th><th>Description</th><th>Type</th><th className="amount">Amount</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.row}>
                    <td>
                      <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                      {r.status === 'duplicate' && job.status !== 'completed' && <label className="checkbox" style={{ fontSize: 12, marginLeft: 6 }}><input type="checkbox" checked={includeDup.has(r.row)} onChange={(e) => setIncludeDup((s) => { const n = new Set(s); e.target.checked ? n.add(r.row) : n.delete(r.row); return n })} />import anyway</label>}
                    </td>
                    <td className="faint" style={{ whiteSpace: 'nowrap' }}>{r.date || r.raw?.[0]}</td>
                    <td style={{ maxWidth: 360 }}><div className="truncate">{r.merchant || r.description}</div>{r.error && <div className="expense" style={{ fontSize: 12 }}>{r.error}</div>}{r.merchant && <div className="faint truncate" style={{ fontSize: 11 }}>{r.description}</div>}</td>
                    <td>{r.type && (job.status === 'completed' ? TYPE_LABEL[r.type] : (
                      <select className="select" style={{ minHeight: 32, padding: '4px 8px' }} value={overrides[r.row] || r.type} onChange={(e) => setOverrides({ ...overrides, [r.row]: e.target.value })} aria-label="Type">
                        {(r.direction === 'in' ? ['income', 'refund', 'adjustment'] : ['expense', 'investment', 'adjustment']).map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
                      </select>
                    ))}</td>
                    <td className={`amount ${r.direction === 'in' ? 'income' : ''}`}>{r.amount ? `${r.direction === 'in' ? '+' : '−'}${Number(r.amount).toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {job.status === 'validated' && (
            <div className="row" style={{ marginTop: 14 }}>
              <Button variant="primary" loading={commit.isPending} disabled={!counts.ok && !includeDup.size} onClick={() => { setError(null); commit.mutate() }}>Import {counts.ok + includeDup.size} transactions</Button>
              <Button onClick={reset}>Cancel</Button>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

function SmsImport() {
  const session = useSession()
  const toast = useToast()
  const { data: accounts = [] } = useAccounts()
  const [text, setText] = useState('')
  const [accountId, setAccountId] = useState(session.settings.default_account_id ? String(session.settings.default_account_id) : '')
  const [parsed, setParsed] = useState(null)
  const [error, setError] = useState(null)
  const [date, setDate] = useState(todayISO())
  const parse = async () => {
    setError(null)
    try { setParsed(await api.post('/sms/parse', { text })) } catch (e) { setParsed(null); setError(e) }
  }
  const save = useLedgerMutation(() => api.post('/sms/commit', { text, account_id: Number(accountId), date }), {
    onSuccess: () => { toast.success('Transaction saved'); setText(''); setParsed(null) }, onError: setError,
  })
  return (
    <div className="grid grid-2">
      <Card title="Paste a bank SMS" sub="Parsed on your machine – nothing is sent anywhere">
        <div className="stack">
          <textarea className="input" rows={5} value={text} onChange={(e) => { setText(e.target.value); setParsed(null) }} placeholder="Dear Customer, INR 340.00 debited from a/c **1234 to SWIGGY on 13-09-26 via UPI…" aria-label="SMS text" />
          <Button icon={MessageSquareText} disabled={text.trim().length < 10} onClick={parse}>Read SMS</Button>
          <FormError error={error} />
          {parsed && (
            <div className="notice success">
              <div className="grow">
                <strong>{TYPE_LABEL[parsed.type]} · <span className="num">₹{parsed.amount}</span></strong>
                <span className="muted" style={{ fontSize: 13 }}>{parsed.description}{parsed.payment_method ? ` · ${parsed.payment_method}` : ''}{parsed.institution ? ` · ${parsed.institution}` : ''}{parsed.ref_id ? ` · ref ${parsed.ref_id}` : ''}</span>
                <div className="form-grid" style={{ marginTop: 10 }}>
                  <Select value={accountId} onChange={(e) => setAccountId(e.target.value)} placeholder="Account…" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} aria-label="Account" />
                  <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date" />
                </div>
                <Button variant="primary" style={{ marginTop: 10 }} disabled={!accountId} loading={save.isPending} onClick={() => save.mutate()}>Save transaction</Button>
              </div>
            </div>
          )}
        </div>
      </Card>
      <Card title="Automatic SMS forwarding">
        <p className="muted" style={{ marginTop: 0 }}>An Android SMS-forwarder app can post bank SMS to Ledgerly automatically. Create a token in <strong>Settings → Integrations</strong>, then configure the app with:</p>
        <div className="stack" style={{ gap: 6, fontSize: 13 }}>
          <div><span className="faint">URL</span> <code>http://&lt;this-computer's-IP&gt;:8000/api/sms/webhook</code></div>
          <div><span className="faint">Header</span> <code>Authorization: Bearer lsms_…</code></div>
          <div><span className="faint">Body</span> <code>{'{"text": "%sms_body%"}'}</code></div>
        </div>
        <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>Forwarded SMS land in your default account marked “to review”. Duplicates (same UPI reference) are ignored.</p>
      </Card>
    </div>
  )
}

function ImportHistory() {
  const q = useQuery({ queryKey: ['imports'], queryFn: () => api.get('/imports') })
  if (q.isLoading) return <Loading />
  if (!q.data?.length) return <Card><Empty icon={Upload} title="No imports yet" /></Card>
  return (
    <Card>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>File</th><th>Format</th><th>Status</th><th className="amount">Imported</th><th className="amount">Duplicates</th><th className="amount">Errors</th><th>When</th></tr></thead>
        <tbody>{q.data.map((j) => <tr key={j.id}><td className="truncate" style={{ maxWidth: 240 }}>{j.filename}</td><td>{j.file_format}</td><td><Badge tone={j.status === 'completed' ? 'success' : j.status === 'cancelled' ? '' : 'warning'}>{j.status}</Badge></td><td className="amount">{j.imported}</td><td className="amount">{j.duplicates}</td><td className="amount">{j.errors}</td><td className="faint">{relativeTime(j.created_at)}</td></tr>)}</tbody>
      </table></div>
    </Card>
  )
}
