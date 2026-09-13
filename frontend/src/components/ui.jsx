import React, { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Canvas, useFrame } from '@react-three/fiber'
import { categories, kindDetails, kinds, paymentMethods } from '../lib/constants'
import { categoryColor, money, monthLabel, shortDate } from '../lib/format'

import { playClick } from '../lib/sound'

export function Icon({ children, name }) {
  if (name === 'overview' || children === '⌂') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    )
  }
  if (name === 'autosync' || children === '⚡') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="#7ef0c2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
      </svg>
    )
  }
  if (name === 'transactions' || children === '↕') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="m7 15 5 5 5-5" /><path d="m7 9 5-5 5 5" />
      </svg>
    )
  }
  if (name === 'accounts' || children === '▣') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect width="20" height="14" x="2" y="5" rx="2" /><line x1="2" x2="22" y1="10" y2="10" />
      </svg>
    )
  }
  if (name === 'investments' || children === '◈') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" />
      </svg>
    )
  }
  if (name === 'budgets' || children === '◒') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21.21 15.89A10 10 0 1 1 8 2.83" /><path d="M22 12A10 10 0 0 0 12 2v10z" />
      </svg>
    )
  }
  if (name === 'bills' || children === '◷') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
      </svg>
    )
  }
  if (name === 'insights' || children === '◉') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="3" />
      </svg>
    )
  }
  if (name === 'goals' || children === '◎') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" />
      </svg>
    )
  }
  if (name === 'settings' || children === '⚙') {
    return (
      <svg className="nav-svg-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    )
  }
  return <span className="nav-icon">{children}</span>
}


export function BackgroundParticles({ particles }) {
  return (
    <div className="starfield" aria-hidden="true">
      {particles.map((particle) => (
        <span
          key={particle.id}
          className="particle"
          style={{
            left: particle.left,
            top: particle.top,
            width: particle.size,
            height: particle.size,
            animationDelay: `${particle.delay}s`,
            animationDuration: `${particle.duration}s`,
            opacity: particle.opacity,
          }}
        />
      ))}
    </div>
  )
}

function Orbit() {
  const ref = React.useRef()
  useFrame((_, delta) => {
    if (ref.current) ref.current.rotation.y += delta * 0.28
  })
  return (
    <group ref={ref} rotation={[0.45, 0.2, 0]}>
      <mesh>
        <torusGeometry args={[1.35, 0.035, 16, 80]} />
        <meshBasicMaterial color="#8ae6ff" />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.58, 32, 32]} />
        <meshStandardMaterial color="#b29bff" emissive="#3a2a63" emissiveIntensity={0.7} />
      </mesh>
      <mesh position={[1.35, 0, 0]}>
        <sphereGeometry args={[0.12, 20, 20]} />
        <meshStandardMaterial color="#7ef0c2" emissive="#123c52" emissiveIntensity={0.8} />
      </mesh>
    </group>
  )
}

export function HeroOrbit({ cashflow, invested, billsDue }) {
  return (
    <div className="hero-orbit">
      <div className="hero-visual-stack">
        <div className="floating-panel panel-a">
          <span className="mini-kicker">Cashflow</span>
          <strong>{money(cashflow)}</strong>
          <small>Income minus spend</small>
        </div>
        <div className="floating-panel panel-b">
          <span className="mini-kicker">Invested</span>
          <strong>{money(invested)}</strong>
          <small>Wealth in motion</small>
        </div>
        <div className="floating-panel panel-c">
          <span className="mini-kicker">Bills</span>
          <strong>{money(billsDue)}</strong>
          <small>Upcoming commitments</small>
        </div>
      </div>
      <Canvas camera={{ position: [0, 0, 4] }}>
        <ambientLight intensity={0.7} />
        <pointLight position={[3, 3, 4]} color="#8ae6ff" />
        <Orbit />
      </Canvas>
    </div>
  )
}

export function AnimatedNumber({ value }) {
  const [display, setDisplay] = useState(0)
  const current = React.useRef(0)
  useEffect(() => {
    const start = current.current
    const diff = value - start
    const startAt = performance.now()
    let frame
    const tick = (now) => {
      const progress = Math.min(1, (now - startAt) / 700)
      const eased = 1 - (1 - progress) ** 3
      const next = start + diff * eased
      current.current = next
      setDisplay(next)
      if (progress < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])
  return <>{money(display)}</>
}

export function CaptureForm({ form, setForm, onSubmit, saving, editing, autoFocus = true }) {
  const detail = kindDetails[form.kind] || kindDetails.expense
  return (
    <form onSubmit={onSubmit} className={`capture-form ${detail.accent}`}>
      <div className="capture-hero">
        <span className="capture-orb">{form.kind === 'expense' ? '↘' : form.kind === 'income' ? '↗' : '◈'}</span>
        <div>
          <span className="section-kicker">{detail.eyebrow}</span>
          <h3>{editing ? `Edit ${detail.title.toLowerCase()}` : detail.title}</h3>
          <p>{detail.hint}</p>
        </div>
      </div>
      <div className="kind-switch">
        {kinds.map((kind) => (
          <button type="button" key={kind.id} className={form.kind === kind.id ? 'active' : ''} onClick={() => setForm({ ...form, kind: kind.id })}>
            {kind.label}
          </button>
        ))}
      </div>
      <label>
        What was it for? <span className="required">required</span>
        <input autoFocus={autoFocus} required value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder={detail.placeholder} />
      </label>
      <div className="form-row">
        <label>
          Amount in INR <span className="required">required</span>
          <input type="number" min="0.01" step="1" required value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} placeholder="0" />
        </label>
        <label>
          Category
          <select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })}>
            {categories.map((category) => (
              <option key={category}>{category}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>
          Payment method
          <select value={form.payment_method} onChange={(event) => setForm({ ...form, payment_method: event.target.value })}>
            {paymentMethods.map((method) => (
              <option key={method}>{method}</option>
            ))}
          </select>
        </label>
        <label>
          When
          <input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} />
        </label>
      </div>
      <div className="form-row">
        <label>
          Merchant <span className="optional">optional</span>
          <input value={form.merchant} onChange={(event) => setForm({ ...form, merchant: event.target.value })} placeholder="e.g. Zepto, Swiggy" />
        </label>
        <label className="check-label">
          <input type="checkbox" checked={form.recurring} onChange={(event) => setForm({ ...form, recurring: event.target.checked })} /> Recurring payment
        </label>
      </div>
      <label>
        Note <span className="optional">optional</span>
        <input value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} placeholder="Add a little context" />
      </label>
      <button className="primary-button" disabled={saving}>
        {saving ? 'Saving...' : editing ? 'Save changes' : `Save ${form.kind}`} <span>↗</span>
      </button>
    </form>
  )
}

export function TransactionRow({ item, onDelete, onEdit }) {
  return (
    <motion.div className={`transaction-row kind-${item.kind || 'expense'}`} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}>
      <span className="category-badge" style={{ color: categoryColor(item.category) }}>{(item.category || 'O').slice(0, 1)}</span>
      <div className="transaction-info">
        <strong>
          {item.title} {item.recurring ? <small className="recurring-tag">RECURRING</small> : null}
        </strong>
        <span>
          {item.kind === 'income' ? 'Income' : item.kind === 'investment' ? 'Investment' : item.category || 'Other'}
          {item.payment_method ? ` · ${item.payment_method}` : ''}
          {item.merchant ? ` · ${item.merchant}` : ''}
        </span>
      </div>
      <time>{shortDate(item.date)}</time>
      <b className={`transaction-amount ${item.kind || 'expense'}`}>{item.kind === 'income' ? '+' : item.kind === 'expense' ? '−' : ''}{money(item.amount)}</b>
      <button className="icon-button edit-button" onClick={() => onEdit(item)} aria-label={`Edit ${item.title}`}>✎</button>
      <button className="icon-button delete-button" onClick={() => onDelete(item)} aria-label={`Delete ${item.title}`}>×</button>
    </motion.div>
  )
}

export function SpendingBars({ breakdown, maxCategory }) {
  if (!breakdown.length) return <div className="empty-chart">Your first category will bloom here.</div>
  return (
    <div className="bars">
      {breakdown.slice(0, 6).map((item, index) => (
        <div className="bar-row" key={item.category}>
          <div className="bar-label">
            <span>
              <i style={{ background: item.color }} />
              {item.category}
            </span>
            <b>{money(item.amount)}</b>
          </div>
          <div className="bar-track">
            <motion.div initial={{ width: 0 }} animate={{ width: `${(item.amount / maxCategory) * 100}%` }} transition={{ duration: 0.7, delay: index * 0.08 }} style={{ background: item.color }} />
          </div>
        </div>
      ))}
    </div>
  )
}

export function DonutChart({ breakdown }) {
  const total = breakdown.reduce((sum, item) => sum + item.amount, 0) || 1
  const radius = 68
  const circumference = 2 * Math.PI * radius
  let offset = 0
  if (!breakdown.length) return <div className="empty-chart">Add spend to see the mix.</div>
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 180 180" className="donut-svg">
        <circle cx="90" cy="90" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="16" />
        {breakdown.slice(0, 7).map((item) => {
          const length = (item.amount / total) * circumference
          const circle = (
            <circle
              key={item.category}
              cx="90"
              cy="90"
              r={radius}
              fill="none"
              stroke={item.color}
              strokeWidth="16"
              strokeDasharray={`${length} ${circumference - length}`}
              strokeDashoffset={-offset}
              strokeLinecap="round"
              transform="rotate(-90 90 90)"
            />
          )
          offset += length
          return circle
        })}
        <text x="90" y="86" textAnchor="middle" fill="#edf6ff" fontSize="16" fontWeight="700">{money(total)}</text>
        <text x="90" y="106" textAnchor="middle" fill="#9bb0c4" fontSize="10">SPEND MIX</text>
      </svg>
      <ul className="donut-legend">
        {breakdown.slice(0, 5).map((item) => (
          <li key={item.category}>
            <i style={{ background: item.color }} />
            <span>{item.category}</span>
            <b>{Math.round((item.amount / total) * 100)}%</b>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function TrendChart({ series }) {
  const max = Math.max(...series.flatMap((item) => [item.expense, item.income]), 1)
  const points = (key) =>
    series
      .map((item, index) => {
        const x = (index / Math.max(series.length - 1, 1)) * 320
        const y = 110 - (item[key] / max) * 96
        return `${x},${y}`
      })
      .join(' ')

  if (!series.length) return <div className="empty-chart">Trends appear after a few months of entries.</div>
  return (
    <div className="trend-wrap">
      <svg viewBox="0 0 320 130" className="trend-svg" preserveAspectRatio="none">
        <defs>
          <linearGradient id="incomeGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#7ef0c2" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#7ef0c2" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="expenseGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff8fab" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#ff8fab" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline fill="none" stroke="#ff8fab" strokeWidth="2.5" strokeLinecap="round" points={points('expense')} />
        <polyline fill="none" stroke="#7ef0c2" strokeWidth="2.5" strokeLinecap="round" points={points('income')} />
      </svg>
      <div className="trend-axis">
        {series.map((item) => (
          <span key={item.month}>{monthLabel(item.month).replace(' ', '\n')}</span>
        ))}
      </div>
      <div className="trend-legend">
        <span><i className="income" /> Income</span>
        <span><i className="expense" /> Spend</span>
      </div>
    </div>
  )
}

export function MetricCards({ expenses, income, investments, cashflow, count, healthScore, burnRate }) {
  return (
    <section className="metric-grid four">
      <motion.div className="metric-card featured" whileHover={{ y: -4, scale: 1.01 }}>
        <span className="metric-label">SPENDS TRACKED</span>
        <strong><AnimatedNumber value={expenses} /></strong>
        <div className="metric-foot">
          <span className="trend-up">INR · ₹</span> Across {count} transactions
        </div>
        <div className="sparkline"><i /><i /><i /><i /><i /><i /><i /><i /></div>
      </motion.div>
      <motion.div className="metric-card" whileHover={{ y: -4, scale: 1.01 }}>
        <span className="metric-label">INCOME</span>
        <strong><AnimatedNumber value={income} /></strong>
        <div className="metric-foot">Salary, refunds and inflow</div>
      </motion.div>
      <motion.div className="metric-card" whileHover={{ y: -4, scale: 1.01 }}>
        <span className="metric-label">INVESTED</span>
        <strong><AnimatedNumber value={investments} /></strong>
        <div className="metric-foot">SIPs, funds and deposits</div>
      </motion.div>
      <motion.div className="metric-card" whileHover={{ y: -4, scale: 1.01 }}>
        <span className="metric-label">CASHFLOW</span>
        <strong className={cashflow >= 0 ? 'positive' : 'negative'}><AnimatedNumber value={cashflow} /></strong>
        <div className="metric-foot">
          {healthScore ? (
            <span className="health-mini-pill">Health: {healthScore}/100</span>
          ) : cashflow >= 0 ? (
            'Surplus this view'
          ) : (
            'Spending ahead of income'
          )}
        </div>
      </motion.div>
    </section>
  )
}


export function PanelHeading({ kicker, title, action }) {
  return (
    <div className="panel-heading">
      <div>
        <span className="section-kicker">{kicker}</span>
        <h2>{title}</h2>
      </div>
      {action && <span className="period-pill">{action}</span>}
    </div>
  )
}

export function PageIntro({ kicker, title, copy, action }) {
  return (
    <section className="page-intro">
      <div>
        <p className="eyebrow">{kicker}</p>
        <h1>{title}</h1>
        <p className="intro-copy">{copy}</p>
      </div>
      {action}
    </section>
  )
}

export function SettingRow({ title, description, value, toggle, active, onToggle }) {
  return (
    <div className="setting-row">
      <div>
        <strong>{title}</strong>
        <span>{description}</span>
      </div>
      {toggle ? (
        <button className={`toggle ${active ? 'on' : ''}`} onClick={onToggle} aria-label={`Toggle ${title}`}>
          <i />
        </button>
      ) : (
        <span className="setting-value">{value}</span>
      )}
    </div>
  )
}

export function MonthChips({ months, value, onChange }) {
  return (
    <div className="month-chips">
      <button className={value === 'all' ? 'active' : ''} onClick={() => onChange('all')}>All time</button>
      {months.map((month) => (
        <button key={month} className={value === month ? 'active' : ''} onClick={() => onChange(month)}>
          {monthLabel(month)}
        </button>
      ))}
    </div>
  )
}

export function ConfirmDialog({ title, copy, confirmLabel, onConfirm, onCancel }) {
  return (
    <motion.div className="modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onCancel}>
      <motion.div className="capture-modal confirm-modal" initial={{ y: 24, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 24, opacity: 0 }} onClick={(event) => event.stopPropagation()}>
        <h2>{title}</h2>
        <p>{copy}</p>
        <div className="confirm-actions">
          <button className="ghost-button" type="button" onClick={onCancel}>Cancel</button>
          <button className="danger-button" type="button" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </motion.div>
    </motion.div>
  )
}
