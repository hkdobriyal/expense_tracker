import { useQuery } from '@tanstack/react-query'
import { Landmark, Link2, Plus, RefreshCw, Unplug } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, Confirm, Empty, ErrorNote, FormError, Loading, Modal, PageHead, Switch } from '../components/ui'
import { api } from '../lib/api'
import { ACCOUNT_LABEL, relativeTime } from '../lib/format'
import { useLedgerMutation, useSession, useToast } from '../lib/hooks'

const STATUS_TONE = { active: 'success', pending: 'warning', error: 'critical', expired: 'warning', disconnected: '' }

export default function Banks() {
  const session = useSession()
  const toast = useToast()
  const providers = useQuery({ queryKey: ['bank-providers'], queryFn: () => api.get('/banks/providers') })
  const connections = useQuery({ queryKey: ['bank-connections'], queryFn: () => api.get('/banks/connections') })
  const logs = useQuery({ queryKey: ['sync-logs'], queryFn: () => api.get('/banks/sync-logs') })
  const [wizard, setWizard] = useState(null)
  const [result, setResult] = useState(null)
  const [disconnecting, setDisconnecting] = useState(null)
  const [error, setError] = useState(null)

  const start = useLedgerMutation(({ provider, institution }) => api.post('/banks/connections', { provider, institution_id: institution }), {
    onSuccess: (r) => setWizard({ step: 'accounts', ...r, selected: r.accounts.map((a) => a.external_id) }), onError: setError,
  })
  const link = useLedgerMutation(() => api.post(`/banks/connections/${wizard.connection.id}/accounts`, { account_external_ids: wizard.selected }), {
    onSuccess: (r) => { setWizard(null); setResult(r.sync) }, onError: setError,
  })
  const sync = useLedgerMutation((id) => api.post(`/banks/connections/${id}/sync`), { onSuccess: (r) => setResult(r.sync) })
  const disconnect = useLedgerMutation((id) => api.delete(`/banks/connections/${id}`), { onSuccess: () => { toast.success('Disconnected. Accounts and history are kept.'); setDisconnecting(null) } })
  const autoSync = useLedgerMutation(({ id, value }) => api.patch(`/banks/connections/${id}`, { auto_sync: value }))
  const available = (providers.data || []).filter((p) => p.available)

  return (
    <>
      <PageHead kicker="Connect" title="Bank connections" actions={<Button variant="primary" icon={Plus} onClick={() => { setError(null); setWizard({ step: 'provider' }) }}>Add bank</Button>}>
        Synchronisation fetches transactions, skips duplicates, categorises them, updates balances and evaluates your alerts.
      </PageHead>
      {!session.user.is_demo && (
        <div className="notice info" style={{ marginBottom: 16 }}>
          <div>
            <strong>Live bank sync in India needs an Account Aggregator licence</strong>
            RBI's Account Aggregator network only serves registered businesses (FIUs), so direct bank sync isn't available to an individual yet.
            Until then: <Link to="/import">import statements</Link> (CSV, Excel, OFX, PDF) or forward bank SMS (Settings → Integrations).
            Try the full sync flow with the sandbox bank in <strong style={{ display: 'inline' }}>Demo mode</strong> (sign out → “Try the demo”).
          </div>
        </div>
      )}
      <ErrorNote error={connections.error} onRetry={connections.refetch} />
      {connections.isLoading ? <Loading /> : !connections.data?.length ? (
        <Card><Empty icon={Landmark} title="No banks connected" action={<Button icon={Plus} onClick={() => setWizard({ step: 'provider' })}>See providers</Button>}>Connected accounts sync automatically every few hours while the background worker runs.</Empty></Card>
      ) : (
        <div className="cards">
          {connections.data.map((c) => (
            <Card key={c.id}>
              <div className="row between"><span className="avatar"><Landmark size={17} /></span><Badge tone={STATUS_TONE[c.status]}>{c.status}</Badge></div>
              <h3 style={{ margin: '12px 0 2px' }}>{c.institution_name}</h3>
              <div className="faint" style={{ fontSize: 13 }}>{c.provider === 'demo' ? 'Sandbox provider' : c.provider} · last synced {relativeTime(c.last_synced_at)}</div>
              {c.last_error && <div className="expense" style={{ fontSize: 13, marginTop: 8 }}>{c.last_error}</div>}
              <div className="list" style={{ margin: '10px 0' }}>{c.accounts.map((a) => <div key={a.id} className="list-row" style={{ padding: '6px 0' }}><span className="grow">{a.name}</span><span className="faint" style={{ fontSize: 12 }}>{ACCOUNT_LABEL[a.type]} ••{a.account_number_mask}</span></div>)}</div>
              <div className="row between">
                <label className="row" style={{ fontSize: 13 }}><Switch checked={c.auto_sync} label="Auto-sync" onChange={(value) => autoSync.mutate({ id: c.id, value })} disabled={c.status === 'disconnected'} />Auto-sync</label>
                <div className="row" style={{ gap: 4 }}>
                  <Button size="sm" variant="primary" icon={RefreshCw} loading={sync.isPending && sync.variables === c.id} disabled={c.status === 'disconnected'} onClick={() => sync.mutate(c.id)}>Sync now</Button>
                  {c.status !== 'disconnected' && <Button size="sm" variant="ghost" icon={Unplug} aria-label="Disconnect" onClick={() => setDisconnecting(c)} />}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
      {logs.data?.length > 0 && (
        <Card title="Sync history" style={{ marginTop: 16 }}>
          <div className="table-wrap"><table className="table">
            <thead><tr><th>When</th><th>Trigger</th><th>Status</th><th className="amount">Imported</th><th className="amount">Updated</th><th className="amount">Duplicates</th><th className="hide-mobile">Message</th></tr></thead>
            <tbody>{logs.data.map((l) => <tr key={l.id}><td>{relativeTime(l.started_at)}</td><td>{l.trigger}</td><td><Badge tone={l.status === 'success' ? 'success' : l.status === 'failed' ? 'critical' : 'warning'}>{l.status}</Badge></td><td className="amount">{l.imported}</td><td className="amount">{l.updated}</td><td className="amount">{l.duplicates}</td><td className="hide-mobile faint">{l.message}</td></tr>)}</tbody>
          </table></div>
        </Card>
      )}

      <Modal open={!!wizard} onClose={() => setWizard(null)} kicker={wizard?.step === 'accounts' ? 'Step 2 of 2' : 'Step 1 of 2'} title={wizard?.step === 'accounts' ? 'Choose accounts to link' : 'Add a bank'}>
        {wizard?.step === 'provider' && (
          <div className="stack">
            {(providers.data || []).map((p) => (
              <div key={p.key} className="notice" style={{ opacity: p.available ? 1 : 0.7 }}>
                <div className="grow">
                  <strong>{p.label} {p.sandbox && <Badge tone="warning">sandbox</Badge>}</strong>
                  <span className="muted" style={{ fontSize: 13 }}>{p.available ? p.description : p.reason}</span>
                  {p.available && p.institutions.map((i) => (
                    <div key={i.id} className="row" style={{ marginTop: 10 }}>
                      <span className="grow">{i.name}</span>
                      <Button size="sm" variant="primary" icon={Link2} loading={start.isPending} onClick={() => start.mutate({ provider: p.key, institution: i.id })}>Connect</Button>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {!available.length && <p className="faint" style={{ fontSize: 13, margin: 0 }}>No provider is available for this workspace. See docs/bank-integration.md for what each provider needs.</p>}
            <FormError error={error} />
          </div>
        )}
        {wizard?.step === 'accounts' && (
          <div className="stack">
            <p className="muted" style={{ margin: 0 }}>{wizard.message}</p>
            {wizard.accounts.map((a) => (
              <label key={a.external_id} className="checkbox notice">
                <input type="checkbox" checked={wizard.selected.includes(a.external_id)} onChange={(e) => setWizard({ ...wizard, selected: e.target.checked ? [...wizard.selected, a.external_id] : wizard.selected.filter((x) => x !== a.external_id) })} />
                <span className="grow">{a.name}</span><span className="faint">{ACCOUNT_LABEL[a.type]} ••{a.mask}</span>
              </label>
            ))}
            <FormError error={error} />
            <div className="modal-foot"><Button onClick={() => setWizard(null)}>Cancel</Button><Button variant="primary" loading={link.isPending} disabled={!wizard.selected.length} onClick={() => link.mutate()}>Link & sync</Button></div>
          </div>
        )}
      </Modal>
      <Modal open={!!result} onClose={() => setResult(null)} title={result?.status === 'success' ? 'Synchronisation completed' : 'Synchronisation failed'} footer={<Button variant="primary" onClick={() => setResult(null)}>Done</Button>}>
        {result && (result.status === 'success' ? (
          <div className="grid grid-3">
            <div><div className="num" style={{ fontSize: 28, fontWeight: 700 }}>{result.imported}</div><div className="faint">imported</div></div>
            <div><div className="num" style={{ fontSize: 28, fontWeight: 700 }}>{result.updated}</div><div className="faint">updated</div></div>
            <div><div className="num" style={{ fontSize: 28, fontWeight: 700 }}>{result.duplicates}</div><div className="faint">duplicates skipped</div></div>
          </div>
        ) : <div className="form-error">{result.message}</div>)}
        {result && <p className="faint" style={{ marginBottom: 0 }}>Fetched {result.fetched} · finished {relativeTime(result.finished_at)}</p>}
      </Modal>
      <Confirm open={!!disconnecting} onClose={() => setDisconnecting(null)} title={`Disconnect ${disconnecting?.institution_name}?`} message="Stored access is deleted. Linked accounts and their transactions stay in Ledgerly." confirmLabel="Disconnect" loading={disconnect.isPending} onConfirm={() => disconnect.mutate(disconnecting.id)} />
    </>
  )
}
