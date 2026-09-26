import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  ArrowDownLeft, ArrowUpRight, CalendarClock, Check, CreditCard, Gauge, Landmark, Lightbulb, PiggyBank, Plus, Scale, TrendingUp, Upload, Wallet, X,
} from 'lucide-react'
import { Suspense, lazy } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CategoryDonut, HBars, IncomeExpenseChart } from '../components/charts'
import { useActions } from '../components/Layout'
import PeriodPicker, { periodParams, periodReady, usePeriod } from '../components/PeriodPicker'
import { Badge, Button, Card, Empty, ErrorNote, Loading, Money, Progress, Stat } from '../components/ui'
import { api } from '../lib/api'
import { ACCOUNT_LABEL, daysUntil, money, pct, shortDate, signedAmount } from '../lib/format'
import { useLedgerMutation, useSession } from '../lib/hooks'

const Hero3D = lazy(() => import('../components/Hero3D'))

export default function Dashboard() {
  const session = useSession()
  const [period, setPeriod] = usePeriod()
  const dash = useQuery({ queryKey: ['dashboard', period], queryFn: () => api.get('/dashboard', periodParams(period)), enabled: !!periodReady(period) })
  const d = dash.data
  const cur = d?.currency || session.settings.base_currency

  return (
    <div className="stack" style={{ gap: 18 }}>
      <div className="page-head" style={{ marginBottom: 0 }}>
        <div>
          <div className="kicker">{new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long' })}</div>
          <h2>Hello{session.user.display_name ? `, ${session.user.display_name}` : ''}</h2>
        </div>
        <PeriodPicker value={period} onChange={setPeriod} />
      </div>
      <ErrorNote error={dash.error} onRetry={dash.refetch} />
      {!d ? <Loading rows={8} /> : (
        <>
          {!d.onboarding.dismissed && !d.onboarding.complete && <Onboarding steps={d.onboarding.steps} />}
          <div className="grid grid-4">
            <Card className="hero span-2 stat">
              <Suspense fallback={null}><Hero3D positive={d.totals.net_cash_flow >= 0} /></Suspense>
              <div style={{ position: 'relative' }}>
                <div className="label"><span className="stat-icon"><Wallet size={16} /></span>Total balance</div>
                <div className="value"><Money minor={d.total_balance} currency={cur} animated /></div>
                <div className="meta">Current, savings, cash & wallets</div>
                <div className="row wrap" style={{ marginTop: 18, gap: 18 }}>
                  <div><div className="faint" style={{ fontSize: 12 }}>Net worth</div><Money minor={d.net_worth.net_worth} currency={cur} className="" /></div>
                  <div><div className="faint" style={{ fontSize: 12 }}>Net cash flow · {d.period.label}</div><Money minor={d.totals.net_cash_flow} currency={cur} sign className={d.totals.net_cash_flow >= 0 ? 'income' : 'expense'} /></div>
                </div>
                {d.net_worth.missing_rates.length > 0 && <div className="faint" style={{ fontSize: 12, marginTop: 8 }}>Excludes {d.net_worth.missing_rates.join(', ')} accounts – add an exchange rate in Settings.</div>}
              </div>
            </Card>
            <Stat label="Income" icon={ArrowDownLeft} value={d.totals.income} currency={cur} delta={d.comparison.income} meta={`vs ${d.period.previous_label}`} />
            <Stat label="Expenses" icon={ArrowUpRight} value={d.totals.expenses} currency={cur} delta={d.comparison.expenses} invert meta={d.totals.refunds ? `after ${money(d.totals.refunds, cur)} refunds` : `vs ${d.period.previous_label}`} />
            <Stat label="Saved" icon={PiggyBank} value={d.totals.savings} currency={cur} delta={d.comparison.savings} meta={d.totals.invested ? `incl. ${money(d.totals.invested, cur)} invested` : 'income − expenses'} />
            <Stat label="Savings rate" icon={TrendingUp} value={pct(d.totals.savings_rate)} meta={d.totals.income ? 'of income' : 'no income recorded'} />
            <Stat label="Budget remaining" icon={Gauge} value={d.budget.count ? d.budget.remaining : '—'} currency={cur} meta={d.budget.count ? `${money(d.budget.spent, cur)} of ${money(d.budget.limit, cur)}${d.budget.over_count ? ` · ${d.budget.over_count} over` : ''}` : <Link to="/budgets?new=1">Create a budget</Link>} />
            <Stat label="Subscriptions" icon={CreditCard} value={d.subscriptions.active_count ? d.subscriptions.monthly_total : '—'} currency={cur} meta={d.subscriptions.active_count ? `${d.subscriptions.active_count} active · per month` : <Link to="/subscriptions">Track subscriptions</Link>} />
          </div>

          <div className="grid grid-3">
            <Card title="Income vs expenses" sub="Last 6 months" className="span-2" action={<Link to="/analytics" className="faint" style={{ fontSize: 13 }}>Analytics →</Link>}>
              {d.trend.some((p) => p.income || p.expenses) ? <IncomeExpenseChart data={d.trend} currency={cur} /> : <Empty icon={TrendingUp} title="No history yet">Add or import transactions to see your monthly trend.</Empty>}
            </Card>
            <Card title="Spending by category" sub={d.period.label} action={<Link to="/analytics" className="faint" style={{ fontSize: 13 }}>Details →</Link>}>
              {d.categories.some((c) => c.amount > 0) ? (
                <>
                  <CategoryDonut data={d.categories} currency={cur} height={190} />
                  <div style={{ marginTop: 12 }}><HBars items={d.categories.filter((c) => c.amount > 0).slice(0, 5)} currency={cur} /></div>
                </>
              ) : <Empty title="No spending yet">{d.period.label}</Empty>}
            </Card>
          </div>

          <div className="grid grid-3">
            <Card title="Insights" sub="Derived from your data" action={<Lightbulb size={16} className="faint" />}>
              {d.insights.length ? (
                <div className="stack" style={{ gap: 10 }}>
                  {d.insights.map((i, idx) => (
                    <div key={idx} className={`notice ${i.severity}`}>
                      <div><strong>{i.title}</strong><span className="muted" style={{ fontSize: 13 }}>{i.message}</span></div>
                    </div>
                  ))}
                </div>
              ) : <p className="muted" style={{ margin: 0 }}>Insights appear once there is enough activity to compare – nothing is guessed.</p>}
            </Card>
            <Card title="Budgets" sub="Current period" action={<Link to="/budgets" className="faint" style={{ fontSize: 13 }}>All →</Link>}>
              {d.budget.top.length ? (
                <div className="stack">
                  {d.budget.top.map((b) => (
                    <div key={b.id}>
                      <div className="row between" style={{ fontSize: 14, marginBottom: 6 }}><strong>{b.name}</strong><span className="num faint">{money(b.spent, cur)} / {money(b.limit, cur)}</span></div>
                      <Progress value={b.usage_pct} tone={b.status === 'over' ? 'over' : b.status === 'warning' ? 'warning' : ''} label={`${b.name} budget used`} />
                    </div>
                  ))}
                </div>
              ) : <Empty icon={Gauge} title="No budgets" action={<Link className="btn sm" to="/budgets?new=1">Create budget</Link>} />}
            </Card>
            <Card title="Coming up" sub="Next 14 days">
              {d.upcoming_bills.length || d.subscriptions.renewals.length ? (
                <div className="list">
                  {d.upcoming_bills.map((b) => {
                    const days = daysUntil(b.next_due_date)
                    return (
                      <div key={`b${b.id}`} className="list-row">
                        <span className="avatar"><CalendarClock size={16} /></span>
                        <div className="grow"><div className="truncate" style={{ fontWeight: 600 }}>{b.name}</div><div className="faint" style={{ fontSize: 12 }}>{shortDate(b.next_due_date)}{b.autopay ? ' · auto-pay' : ''}</div></div>
                        <div style={{ textAlign: 'right' }}><Money minor={b.amount_minor} currency={b.currency} /><div><Badge tone={days < 0 ? 'critical' : days <= 3 ? 'warning' : ''}>{days < 0 ? `${-days}d overdue` : days === 0 ? 'today' : `in ${days}d`}</Badge></div></div>
                      </div>
                    )
                  })}
                  {d.subscriptions.renewals.map((s) => (
                    <div key={`s${s.id}`} className="list-row">
                      <span className="avatar"><CreditCard size={16} /></span>
                      <div className="grow"><div className="truncate" style={{ fontWeight: 600 }}>{s.name}</div><div className="faint" style={{ fontSize: 12 }}>renews {shortDate(s.next_payment_date)}</div></div>
                      <Money minor={s.amount_minor} currency={s.currency} />
                    </div>
                  ))}
                </div>
              ) : <p className="muted" style={{ margin: 0 }}>Nothing due in the next two weeks.</p>}
            </Card>
          </div>

          <div className="grid grid-3">
            <Card title="Recent activity" className="span-2" action={<Link to="/transactions" className="faint" style={{ fontSize: 13 }}>All transactions →</Link>}>
              {d.recent.length ? <RecentList items={d.recent} /> : <Empty icon={Plus} title="Nothing recorded yet" action={<FirstActions />}>Add a transaction, import a statement, or connect a bank.</Empty>}
            </Card>
            <Card title="Accounts" action={<Link to="/accounts" className="faint" style={{ fontSize: 13 }}>Manage →</Link>}>
              {d.accounts.length ? (
                <div className="list">
                  {d.accounts.map((a) => (
                    <div key={a.id} className="list-row">
                      <span className="avatar">{a.type === 'credit_card' ? <CreditCard size={16} /> : a.type === 'loan' || a.type === 'mortgage' ? <Scale size={16} /> : <Landmark size={16} />}</span>
                      <div className="grow"><div className="truncate" style={{ fontWeight: 600 }}>{a.name}</div><div className="faint" style={{ fontSize: 12 }}>{ACCOUNT_LABEL[a.type]}</div></div>
                      <Money minor={a.balance_minor} currency={a.currency} className={a.balance_minor < 0 ? 'expense' : ''} />
                    </div>
                  ))}
                </div>
              ) : <Empty icon={Wallet} title="No accounts" action={<Link className="btn sm primary" to="/accounts?new=1">Add account</Link>} />}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}

function RecentList({ items }) {
  const { editTransaction } = useActions()
  return (
    <div className="list">
      {items.map((t) => (
        <motion.div key={t.id} layout className="list-row clickable" role="button" tabIndex={0} onClick={() => editTransaction(t)} onKeyDown={(e) => e.key === 'Enter' && editTransaction(t)}>
          <span className="avatar" style={{ background: t.category_color ? `${t.category_color}22` : undefined, color: t.category_color || undefined }}>{(t.merchant || t.description)[0]?.toUpperCase()}</span>
          <div className="grow">
            <div className="truncate" style={{ fontWeight: 600 }}>{t.description}</div>
            <div className="faint truncate" style={{ fontSize: 12 }}>{shortDate(t.date)} · {t.type === 'transfer' ? `${t.account_name} → ${t.transfer_account_name}` : `${t.category || 'Uncategorised'} · ${t.account_name}`}</div>
          </div>
          <Money minor={t.type === 'transfer' ? t.amount_minor : signedAmount(t)} currency={t.currency} sign={t.type !== 'transfer'} className={t.type === 'transfer' ? 'muted' : signedAmount(t) >= 0 ? 'income' : ''} />
        </motion.div>
      ))}
    </div>
  )
}

function FirstActions() {
  const { addTransaction } = useActions()
  const navigate = useNavigate()
  return (
    <div className="row wrap" style={{ justifyContent: 'center' }}>
      <Button variant="primary" icon={Plus} onClick={() => addTransaction()}>Add transaction</Button>
      <Button icon={Upload} onClick={() => navigate('/import')}>Import statement</Button>
    </div>
  )
}

const STEP_LINKS = { account: '/accounts?new=1', transactions: '/import', budget: '/budgets?new=1', goal: '/goals?new=1', notifications: '/alerts' }

function Onboarding({ steps }) {
  const session = useSession()
  const dismiss = useLedgerMutation(() => api.patch('/settings', { onboarding_dismissed: true }), { onSuccess: session.refresh })
  const done = steps.filter((s) => s.done).length
  return (
    <Card title="Get set up" sub={`${done} of ${steps.length} done – optional steps can be skipped`} action={<Button size="sm" variant="ghost" icon={X} onClick={() => dismiss.mutate()}>Dismiss</Button>}>
      <Progress value={(done / steps.length) * 100} tone="success" label="Setup progress" />
      <div className="grid grid-3" style={{ marginTop: 14 }}>
        {steps.map((s) => (
          <div key={s.key} className={`step ${s.done ? 'done' : ''}`}>
            <span className="tick">{s.done && <Check size={13} />}</span>
            {s.done || !STEP_LINKS[s.key] ? s.label : <Link to={STEP_LINKS[s.key]}>{s.label}</Link>}
          </div>
        ))}
      </div>
    </Card>
  )
}
