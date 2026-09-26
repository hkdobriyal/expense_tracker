import { useQuery } from '@tanstack/react-query'
import { BarChart3 } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CashFlowChart, CategoryDonut, HBars, IncomeExpenseChart } from '../components/charts'
import PeriodPicker, { periodParams, periodReady, usePeriod } from '../components/PeriodPicker'
import { Badge, Card, Empty, ErrorNote, Loading, Money, PageHead, Segmented, Stat } from '../components/ui'
import { api } from '../lib/api'
import { money, pct } from '../lib/format'

export default function Analytics() {
  const [period, setPeriod] = usePeriod('30d')
  const [view, setView] = useState('categories')
  const navigate = useNavigate()
  const q = useQuery({ queryKey: ['analytics-summary', period], queryFn: () => api.get('/analytics/summary', periodParams(period)), enabled: !!periodReady(period) })
  const d = q.data
  const cur = d?.currency
  const t = d?.totals
  const p = d?.previous_totals
  const change = (a, b) => (b ? { change_pct: Math.round(((a - b) / Math.abs(b)) * 1000) / 10 } : null)

  return (
    <>
      <PageHead kicker="Insights" title="Analytics" actions={<PeriodPicker value={period} onChange={setPeriod} />}>
        Where money comes from and where it goes. Transfers between your own accounts are excluded.
      </PageHead>
      <ErrorNote error={q.error} onRetry={q.refetch} />
      {!d ? <Loading rows={8} /> : (
        <div className="stack" style={{ gap: 16 }}>
          <div className="grid grid-4">
            <Stat label="Income" value={t.income} currency={cur} delta={change(t.income, p.income)} meta={`vs ${d.period.previous.label}`} />
            <Stat label="Expenses" value={t.expenses} currency={cur} delta={change(t.expenses, p.expenses)} invert meta={`vs ${d.period.previous.label}`} />
            <Stat label="Average daily spend" value={d.average_daily_spend} currency={cur} meta={d.period.label} />
            <Stat label="Savings rate" value={pct(t.savings_rate)} meta={`${money(t.savings, cur)} saved`} />
          </div>
          <Card title="Income vs expenses" sub={`${d.period.label} · by ${d.period.granularity}`}>
            {d.series.some((x) => x.income || x.expenses) ? <IncomeExpenseChart data={d.series} currency={cur} granularity={d.period.granularity} height={280} /> : <Empty icon={BarChart3} title="No transactions in this period" />}
          </Card>
          <Card title="Net cash flow" sub="Income − expenses − invested">
            <CashFlowChart data={d.series} currency={cur} granularity={d.period.granularity} height={200} />
          </Card>
          <Segmented label="Breakdown" value={view} onChange={setView} options={[{ value: 'categories', label: 'Categories' }, { value: 'merchants', label: 'Merchants' }, { value: 'accounts', label: 'Accounts' }, { value: 'income', label: 'Income sources' }]} />
          {view === 'categories' && (
            <div className="grid grid-2">
              <Card title="Spending by category"><CategoryDonut data={d.categories} currency={cur} height={260} onSelect={(c) => c.category_id && navigate(`/transactions?category_id=${c.category_id}&start=${d.period.start}&end=${d.period.end}`)} /></Card>
              <Card title="Compared with the previous period">
                {d.categories.length ? (
                  <div className="list">
                    {d.categories.map((c) => (
                      <details key={c.category_id ?? 'none'} className="list-row" style={{ display: 'block' }}>
                        <summary className="row" style={{ cursor: 'pointer', listStyle: 'none' }}>
                          <span className="dot" style={{ background: c.color }} />
                          <span className="grow truncate" style={{ fontWeight: 600 }}>{c.name}</span>
                          {c.change_pct != null && <Badge tone={c.change_pct > 0 ? 'critical' : 'success'}>{c.change_pct > 0 ? '+' : ''}{c.change_pct}%</Badge>}
                          <Money minor={c.amount} currency={cur} />
                          <span className="faint" style={{ width: 44, textAlign: 'right', fontSize: 12 }}>{c.share}%</span>
                        </summary>
                        {c.children.length > 0 && <div style={{ padding: '8px 0 0 19px' }}><HBars items={c.children.map((x) => ({ ...x, color: c.color }))} currency={cur} max={c.amount} /></div>}
                      </details>
                    ))}
                  </div>
                ) : <Empty title="No spending in this period" />}
              </Card>
            </div>
          )}
          {view === 'merchants' && <Card title="Top merchants">{d.merchants.length ? <HBars items={d.merchants} currency={cur} /> : <Empty title="No merchant data" />}</Card>}
          {view === 'accounts' && <Card title="Spending by account">{d.accounts.length ? <HBars items={d.accounts} currency={cur} /> : <Empty title="No spending" />}</Card>}
          {view === 'income' && <Card title="Income by source">{d.income_sources.length ? <HBars items={d.income_sources} currency={cur} /> : <Empty title="No income in this period" />}</Card>}
        </div>
      )}
    </>
  )
}
