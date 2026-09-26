import { useQuery } from '@tanstack/react-query'
import { Scale, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { NetWorthChart } from '../components/charts'
import { Badge, Card, Empty, ErrorNote, Loading, Money, PageHead, Segmented, Stat } from '../components/ui'
import { api } from '../lib/api'
import { ACCOUNT_LABEL } from '../lib/format'

export default function NetWorth() {
  const [months, setMonths] = useState(12)
  const q = useQuery({ queryKey: ['net-worth', months], queryFn: () => api.get('/net-worth', { months }) })
  const d = q.data
  const cur = d?.currency
  const first = d?.history?.find((p) => p.net_worth !== 0)
  const change = first && d ? d.net_worth - first.net_worth : null
  return (
    <>
      <PageHead kicker="Insights" title="Net worth" actions={<Segmented label="Range" value={months} onChange={setMonths} options={[{ value: 6, label: '6M' }, { value: 12, label: '1Y' }, { value: 24, label: '2Y' }, { value: 60, label: '5Y' }]} />}>
        Assets minus liabilities. History is computed from your ledger at each month end; a daily snapshot is also stored by the worker.
      </PageHead>
      <ErrorNote error={q.error} onRetry={q.refetch} />
      {!d ? <Loading rows={8} /> : !d.accounts.length ? <Card><Empty icon={Scale} title="No accounts yet" action={<Link className="btn primary" to="/accounts?new=1">Add account</Link>}>Add bank accounts, investments, property and loans to see your net worth.</Empty></Card> : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid grid-3">
            <Stat label="Net worth" icon={TrendingUp} value={d.net_worth} currency={cur} meta={change != null ? <>{change >= 0 ? '▲' : '▼'} <Money minor={Math.abs(change)} currency={cur} /> over the range</> : null} />
            <Stat label="Assets" value={d.assets} currency={cur} />
            <Stat label="Liabilities" value={d.liabilities} currency={cur} />
          </div>
          {d.missing_rates.length > 0 && <div className="notice warning"><div><strong>Some accounts are excluded</strong>No exchange rate for {d.missing_rates.join(', ')}. Add one under <Link to="/settings">Settings → Exchange rates</Link>.</div></div>}
          <Card title="History"><NetWorthChart data={d.history} currency={cur} height={300} /></Card>
          <Card title="By account">
            <div className="list">
              {d.accounts.map((a) => (
                <div key={a.id} className="list-row">
                  <div className="grow"><strong>{a.name}</strong> <Badge tone={a.is_liability ? 'critical' : 'success'}>{a.is_liability ? 'liability' : 'asset'}</Badge><div className="faint" style={{ fontSize: 12 }}>{ACCOUNT_LABEL[a.type]}</div></div>
                  <div style={{ textAlign: 'right' }}>
                    <Money minor={a.balance_minor} currency={a.currency} className={a.balance_minor < 0 ? 'expense' : ''} />
                    {a.currency !== cur && <div className="faint" style={{ fontSize: 12 }}>{a.base_minor != null ? <Money minor={a.base_minor} currency={cur} /> : 'no rate'}</div>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  )
}
