import { useQuery } from '@tanstack/react-query'
import { Download, FileSpreadsheet, Printer } from 'lucide-react'
import { useState } from 'react'
import PeriodPicker, { periodParams, periodReady, usePeriod } from '../components/PeriodPicker'
import { Button, Card, Empty, ErrorNote, Loading, PageHead, Segmented } from '../components/ui'
import { api } from '../lib/api'
import { useToast } from '../lib/hooks'

const REPORTS = [
  { value: 'monthly_summary', label: 'Summary' }, { value: 'expenses', label: 'Expenses' }, { value: 'income', label: 'Income' },
  { value: 'budgets', label: 'Budgets' }, { value: 'savings', label: 'Savings' }, { value: 'cash_flow', label: 'Cash flow' },
  { value: 'net_worth', label: 'Net worth' }, { value: 'transactions', label: 'Transactions' },
]

function fmt(value) {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'number' || /^-?\d+(\.\d+)?$/.test(String(value))) {
    const n = Number(value)
    return Number.isInteger(n) && Math.abs(n) < 1000 ? String(n) : n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(value)
}

function Table({ columns, rows }) {
  return (
    <div className="table-wrap"><table className="table">
      <thead><tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j} className={typeof v === 'number' || /^-?\d+(\.\d+)?$/.test(String(v ?? '')) ? 'amount' : ''}>{fmt(v)}</td>)}</tr>)}</tbody>
    </table></div>
  )
}

export default function Reports() {
  const toast = useToast()
  const [report, setReport] = useState('monthly_summary')
  const [period, setPeriod] = usePeriod('this_month')
  const params = periodParams(period)
  const q = useQuery({ queryKey: ['report', report, period], queryFn: () => api.get(`/reports/${report}`, params), enabled: !!periodReady(period) })
  const download = (format) => api.download(`/reports/${report}`, { ...params, format }, `ledgerly-${report}.${format}`).catch((e) => toast.error(e.message))
  const d = q.data
  return (
    <>
      <PageHead kicker="Insights" title="Reports" actions={<>
        <Button icon={Download} onClick={() => download('csv')}>CSV</Button>
        <Button icon={FileSpreadsheet} onClick={() => download('xlsx')}>Excel</Button>
        <Button icon={Printer} onClick={() => window.print()}>Print / PDF</Button>
      </>}>
        Generated from the same ledger as the dashboard. “Print / PDF” uses your browser's Save as PDF – no paid service involved.
      </PageHead>
      <div className="row wrap no-print" style={{ marginBottom: 16, gap: 12 }}>
        <Segmented label="Report" value={report} onChange={setReport} options={REPORTS} />
        <PeriodPicker value={period} onChange={setPeriod} />
      </div>
      <ErrorNote error={q.error} onRetry={q.refetch} />
      {!d ? <Loading rows={8} /> : (
        <Card title={`${d.title} · ${d.period.label}`} sub={`${d.period.start} → ${d.period.end} · amounts in ${d.currency}`}>
          {d.rows.length ? <Table columns={d.columns} rows={d.rows} /> : <Empty title="No data for this period" />}
          {d.summary && <div className="row wrap" style={{ marginTop: 14, gap: 20 }}>{Object.entries(d.summary).map(([k, v]) => <span key={k}><span className="faint">{k}: </span><strong className="num">{fmt(v)}</strong></span>)}</div>}
          {d.extra && <><h3 style={{ fontSize: 15, margin: '22px 0 10px' }}>{d.extra.title}</h3><Table columns={d.extra.columns} rows={d.extra.rows} /></>}
        </Card>
      )}
    </>
  )
}
