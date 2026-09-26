import { useQuery } from '@tanstack/react-query'
import { Equal, Minus, Plus } from 'lucide-react'
import { CashFlowChart, IncomeExpenseChart } from '../components/charts'
import PeriodPicker, { periodParams, periodReady, usePeriod } from '../components/PeriodPicker'
import { Card, ErrorNote, Loading, Money, PageHead } from '../components/ui'
import { api } from '../lib/api'

function Line({ icon: Icon, label, minor, currency, tone, strong }) {
  return (
    <div className="list-row" style={{ fontSize: strong ? 17 : 15 }}>
      <span className="avatar" style={{ width: 30, height: 30 }}>{Icon && <Icon size={15} />}</span>
      <span className="grow" style={{ fontWeight: strong ? 800 : 600 }}>{label}</span>
      <Money minor={minor} currency={currency} className={tone} animated />
    </div>
  )
}

export default function CashFlow() {
  const [period, setPeriod] = usePeriod('this_month')
  const q = useQuery({ queryKey: ['cash-flow', period], queryFn: () => api.get('/cash-flow', periodParams(period)), enabled: !!periodReady(period) })
  const d = q.data
  const cur = d?.currency
  return (
    <>
      <PageHead kicker="Insights" title="Cash flow" actions={<PeriodPicker value={period} onChange={setPeriod} />}>
        Opening balance + income − expenses − invested = closing balance, across current, savings, cash, wallet and card accounts.
      </PageHead>
      <ErrorNote error={q.error} onRetry={q.refetch} />
      {!d ? <Loading rows={8} /> : (
        <div className="grid grid-3">
          <Card title={d.label} sub={`${d.start} → ${d.end}`}>
            <div className="list">
              <Line label="Opening balance" minor={d.opening_balance} currency={cur} />
              <Line icon={Plus} label="Income" minor={d.income} currency={cur} tone="income" />
              <Line icon={Minus} label="Expenses (net of refunds)" minor={d.expenses} currency={cur} tone="expense" />
              <Line icon={Minus} label="Invested" minor={d.invested} currency={cur} />
              {d.adjustments !== 0 && <Line icon={Plus} label="Adjustments" minor={d.adjustments} currency={cur} />}
              <Line icon={Equal} label="Net cash flow" minor={d.net_cash_flow} currency={cur} tone={d.net_cash_flow >= 0 ? 'income' : 'expense'} strong />
              <Line label="Closing balance" minor={d.closing_balance} currency={cur} strong />
            </div>
            {d.missing_rates.length > 0 && <p className="faint" style={{ fontSize: 12 }}>Accounts in {d.missing_rates.join(', ')} are excluded until an exchange rate is added.</p>}
            <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>Transfers between your own accounts never count as income or spending.</p>
          </Card>
          <Card title="Monthly cash flow" sub="Last 12 months" className="span-2">
            <IncomeExpenseChart data={d.monthly} currency={cur} height={220} />
            <div style={{ marginTop: 12 }}><CashFlowChart data={d.monthly} currency={cur} height={160} /></div>
          </Card>
          {d.daily.length > 0 && <Card title="Daily net flow" className="span-2"><CashFlowChart data={d.daily} currency={cur} granularity="day" height={200} /></Card>}
        </div>
      )}
    </>
  )
}
