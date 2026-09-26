import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useReducedMotion } from 'framer-motion'
import { money, monthLabel, shortDate } from '../lib/format'

const AXIS = { stroke: 'var(--text-3)', fontSize: 11, tickLine: false, axisLine: false }
export const SERIES = { income: 'var(--income)', expenses: 'var(--expense)', invested: 'var(--violet)', net: 'var(--accent)', assets: 'var(--mint)', liabilities: 'var(--expense)' }

function bucketLabel(bucket, granularity) {
  return granularity === 'month' ? monthLabel(bucket) : shortDate(bucket)
}

function MoneyTooltip({ active, payload, label, currency, granularity }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="t">{granularity ? bucketLabel(label, granularity) : label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="row" style={{ gap: 8 }}>
          <span className="dot" style={{ background: p.color }} />
          <span className="muted" style={{ textTransform: 'capitalize' }}>{p.name}</span>
          <strong className="num" style={{ marginLeft: 'auto' }}>{money(p.value, currency)}</strong>
        </div>
      ))}
    </div>
  )
}

const compact = (currency) => (v) => money(v, currency, { compact: true })

export function IncomeExpenseChart({ data, currency, granularity = 'month', height = 260 }) {
  const reduce = useReducedMotion()
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} barGap={4} margin={{ left: 0, right: 4, top: 8 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="bucket" tickFormatter={(b) => bucketLabel(b, granularity)} {...AXIS} minTickGap={12} />
        <YAxis tickFormatter={compact(currency)} {...AXIS} width={64} />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<MoneyTooltip currency={currency} granularity={granularity} />} />
        <Bar dataKey="income" name="Income" fill={SERIES.income} radius={[6, 6, 0, 0]} maxBarSize={28} isAnimationActive={!reduce} />
        <Bar dataKey="expenses" name="Expenses" fill={SERIES.expenses} radius={[6, 6, 0, 0]} maxBarSize={28} isAnimationActive={!reduce} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function CashFlowChart({ data, currency, granularity = 'month', height = 240, dataKey = 'net', name = 'Net cash flow' }) {
  const reduce = useReducedMotion()
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ left: 0, right: 4, top: 8 }}>
        <defs>
          <linearGradient id={`g-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.45} />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="bucket" tickFormatter={(b) => bucketLabel(b, granularity)} {...AXIS} minTickGap={12} />
        <YAxis tickFormatter={compact(currency)} {...AXIS} width={64} />
        <Tooltip content={<MoneyTooltip currency={currency} granularity={granularity} />} />
        <Area type="monotone" dataKey={dataKey} name={name} stroke="var(--accent)" strokeWidth={2.4} fill={`url(#g-${dataKey})`} isAnimationActive={!reduce} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function NetWorthChart({ data, currency, height = 260 }) {
  const reduce = useReducedMotion()
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey="date" tickFormatter={monthLabel} {...AXIS} />
        <YAxis tickFormatter={compact(currency)} {...AXIS} width={64} />
        <Tooltip content={<MoneyTooltip currency={currency} />} labelFormatter={monthLabel} />
        <Line type="monotone" dataKey="net_worth" name="Net worth" stroke="var(--accent)" strokeWidth={2.6} dot={false} isAnimationActive={!reduce} />
        <Line type="monotone" dataKey="assets" name="Assets" stroke="var(--mint)" strokeWidth={1.6} dot={false} strokeDasharray="4 4" isAnimationActive={!reduce} />
        <Line type="monotone" dataKey="liabilities" name="Liabilities" stroke="var(--expense)" strokeWidth={1.6} dot={false} strokeDasharray="4 4" isAnimationActive={!reduce} />
      </LineChart>
    </ResponsiveContainer>
  )
}

const FALLBACK = ['#8ae6ff', '#b29bff', '#7ef0c2', '#ffd8a8', '#ff8fab', '#70d6ff', '#f7b267', '#95d5b2', '#c8b6ff']

export function CategoryDonut({ data, currency, height = 220, onSelect }) {
  const reduce = useReducedMotion()
  const positive = data.filter((d) => d.amount > 0)
  const total = positive.reduce((s, d) => s + d.amount, 0)
  return (
    <div style={{ position: 'relative', height }}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Pie data={positive} dataKey="amount" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={2} stroke="none" isAnimationActive={!reduce} onClick={(d) => onSelect?.(d)}>
            {positive.map((d, i) => <Cell key={d.category_id ?? i} fill={d.color || FALLBACK[i % FALLBACK.length]} style={{ cursor: onSelect ? 'pointer' : 'default' }} />)}
          </Pie>
          <Tooltip content={({ active, payload }) => active && payload?.length ? (
            <div className="chart-tooltip"><div className="t">{payload[0].name}</div><span className="num">{money(payload[0].value, currency)}</span> <span className="muted">· {payload[0].payload.share}%</span></div>
          ) : null} />
        </PieChart>
      </ResponsiveContainer>
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none', textAlign: 'center' }}>
        <div><div className="faint" style={{ fontSize: 11, fontWeight: 700, letterSpacing: '.1em' }}>SPENT</div><div className="num" style={{ fontSize: 18, fontWeight: 700 }}>{money(total, currency, { compact: total >= 10_000_000 })}</div></div>
      </div>
    </div>
  )
}

export function HBars({ items, currency, max, colorKey = 'color' }) {
  const top = max ?? Math.max(1, ...items.map((i) => i.amount))
  return (
    <div className="stack" style={{ gap: 10 }}>
      {items.map((item, i) => (
        <div key={item.name + i}>
          <div className="row between" style={{ fontSize: 13, marginBottom: 5 }}>
            <span className="row truncate" style={{ gap: 8 }}><span className="dot" style={{ background: item[colorKey] || FALLBACK[i % FALLBACK.length] }} />{item.name}</span>
            <span className="num">{money(item.amount, currency)}</span>
          </div>
          <div className="progress" style={{ height: 6 }}><div style={{ width: `${Math.max(2, (item.amount / top) * 100)}%`, background: item[colorKey] || FALLBACK[i % FALLBACK.length] }} /></div>
        </div>
      ))}
    </div>
  )
}
