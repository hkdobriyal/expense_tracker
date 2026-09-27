import { AnimatePresence, animate, motion, useReducedMotion } from 'framer-motion'
import { Loader2, X } from 'lucide-react'
import { cloneElement, isValidElement, useEffect, useId, useRef, useState } from 'react'
import { money } from '../lib/format'
import { Tilt } from './motion'

export function Button({ variant, size, icon: Icon, loading, children, className = '', ...props }) {
  const cls = ['btn', variant, size, !children && Icon ? 'icon' : '', className].filter(Boolean).join(' ')
  return (
    <button type="button" className={cls} disabled={loading || props.disabled} aria-busy={loading || undefined} {...props}>
      {loading ? <Loader2 size={16} className="spin" aria-hidden /> : Icon ? <Icon size={16} aria-hidden /> : null}
      {children}
    </button>
  )
}

// Cards fade/slide in as they scroll into view; `tilt` adds a 3D pointer tilt.
export function Card({ title, sub, action, children, className = '', hover, tilt, ...props }) {
  const reduce = useReducedMotion()
  const reveal = reduce ? {} : { initial: { opacity: 0, y: 18 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, amount: 0.1 }, transition: { duration: 0.45, ease: [0.22, 1, 0.36, 1] } }
  const content = (
    <>
      {(title || action) && (
        <div className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {action}
        </div>
      )}
      {children}
    </>
  )
  if (tilt) {
    return (
      <motion.div {...reveal} style={{ display: 'grid' }} className={className.includes('span-2') ? 'span-2' : ''}>
        <Tilt className={`card ${hover ? 'hover' : ''} ${className.replace('span-2', '')}`} max={5} {...props}>{content}</Tilt>
      </motion.div>
    )
  }
  return <motion.section className={`card ${hover ? 'hover' : ''} ${className}`} {...reveal} {...props}>{content}</motion.section>
}

export function PageHead({ kicker, title, children, actions }) {
  return (
    <div className="page-head">
      <div>
        {kicker && <div className="kicker">{kicker}</div>}
        <h2>{title}</h2>
        {children && <p>{children}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </div>
  )
}

export function AnimatedNumber({ value, format = (v) => v }) {
  const reduce = useReducedMotion()
  const [display, setDisplay] = useState(value)
  const prev = useRef(value)
  useEffect(() => {
    if (reduce || typeof value !== 'number') {
      setDisplay(value)
      return undefined
    }
    const controls = animate(prev.current ?? 0, value, { duration: 0.6, ease: 'easeOut', onUpdate: (v) => setDisplay(Math.round(v)) })
    prev.current = value
    return () => controls.stop()
  }, [value, reduce])
  return <>{format(display)}</>
}

export function Money({ minor, currency = 'INR', animated, sign, className = '', compact }) {
  const cls = `num ${className}`
  if (animated && typeof minor === 'number') return <span className={cls}><AnimatedNumber value={minor} format={(v) => money(v, currency, { sign, compact })} /></span>
  return <span className={cls}>{money(minor, currency, { sign, compact })}</span>
}

export function Stat({ label, icon: Icon, value, currency = 'INR', meta, delta, invert, animated = true, children }) {
  const pctChange = delta?.change_pct
  const good = pctChange == null ? null : invert ? pctChange <= 0 : pctChange >= 0
  return (
    <Card className="stat" tilt>
      <div className="label">{Icon && <span className="stat-icon"><Icon size={16} aria-hidden /></span>}{label}</div>
      <div className="value">{typeof value === 'number' ? <Money minor={value} currency={currency} animated={animated} /> : value}</div>
      <div className="meta">
        {pctChange != null && <span className={`delta ${good ? 'up' : 'down'}`}>{pctChange > 0 ? '+' : ''}{pctChange}%</span>}
        {meta}
      </div>
      {children}
    </Card>
  )
}

// Associates the label with its control via id/htmlFor and exposes the hint through
// aria-describedby, so screen readers (and tests) get a clean accessible name.
export function Field({ label, hint, required, children, className = '' }) {
  const id = useId()
  const hintId = hint ? `${id}-hint` : undefined
  const child = isValidElement(children)
    ? cloneElement(children, { id: children.props.id || id, 'aria-describedby': hintId, 'aria-required': required || undefined })
    : children
  return (
    <div className={`field ${className}`}>
      <label htmlFor={isValidElement(children) ? child.props.id : undefined}>{label}{required && <span className="req" aria-hidden> *</span>}</label>
      {child}
      {hint && <span className="hint" id={hintId}>{hint}</span>}
    </div>
  )
}

export function Select({ options, placeholder, ...props }) {
  return (
    <select className="select" {...props}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((o) => (o.group ? (
        <optgroup key={o.group} label={o.group}>{o.options.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}</optgroup>
      ) : <option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  )
}

export function Switch({ checked, onChange, label, disabled }) {
  return <button type="button" role="switch" aria-checked={!!checked} aria-label={label} className="switch" disabled={disabled} onClick={() => onChange(!checked)} />
}

export function Segmented({ value, onChange, options, label }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  )
}

export function Badge({ tone, children }) {
  return <span className={`badge ${tone || ''}`}>{children}</span>
}

export function Progress({ value, tone, label }) {
  const reduce = useReducedMotion()
  const width = Math.max(0, Math.min(100, value || 0))
  return (
    <div className={`progress ${tone || ''}`} role="progressbar" aria-valuenow={Math.round(value || 0)} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
      <motion.div initial={{ width: reduce ? `${width}%` : 0 }} animate={{ width: `${width}%` }} transition={{ duration: 0.7, ease: 'easeOut' }} />
    </div>
  )
}

export function Empty({ icon: Icon, title, children, action }) {
  return (
    <div className="empty">
      {Icon && <div className="icon"><Icon size={26} aria-hidden /></div>}
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function Skeleton({ height = 18, width = '100%', style }) {
  return <div className="skeleton" style={{ height, width, ...style }} aria-hidden />
}

export function Loading({ rows = 4 }) {
  return <div className="stack" aria-busy="true" aria-label="Loading">{Array.from({ length: rows }, (_, i) => <Skeleton key={i} height={i === 0 ? 28 : 18} width={i % 2 ? '70%' : '100%'} />)}</div>
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="notice critical" role="alert">
      <div className="grow"><strong>Something went wrong</strong>{error.message}</div>
      {onRetry && <Button size="sm" onClick={onRetry}>Retry</Button>}
    </div>
  )
}

export function Modal({ open, onClose, title, kicker, children, footer, wide }) {
  const titleId = useId()
  const ref = useRef(null)
  // Keep the latest onClose without re-running the effect (callers pass inline arrows);
  // re-running it would steal focus back to the first field on every keystroke.
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    const onKey = (e) => {
      if (e.key === 'Escape') closeRef.current()
      if (e.key === 'Tab' && ref.current) {
        const focusable = ref.current.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
        if (!focusable.length) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    setTimeout(() => ref.current?.querySelector('input, select, textarea, button:not(.close)')?.focus(), 30)
    return () => { document.removeEventListener('keydown', onKey); previous?.focus?.() }
  }, [open])
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
          <motion.div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} className={`modal ${wide ? 'wide' : ''}`} initial={{ y: 24, opacity: 0, scale: 0.98 }} animate={{ y: 0, opacity: 1, scale: 1 }} exit={{ y: 24, opacity: 0 }} transition={{ type: 'spring', damping: 26, stiffness: 320 }}>
            <div className="modal-head">
              <div>
                {kicker && <div className="kicker">{kicker}</div>}
                <h2 id={titleId}>{title}</h2>
              </div>
              <Button variant="ghost" icon={X} className="close" aria-label="Close" onClick={onClose} />
            </div>
            {children}
            {footer && <div className="modal-foot">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

export function Confirm({ open, title, message, confirmLabel = 'Delete', danger = true, onConfirm, onClose, loading }) {
  return (
    <Modal open={open} onClose={onClose} title={title} footer={<>
      <Button onClick={onClose}>Cancel</Button>
      <Button variant={danger ? 'danger solid' : 'primary'} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
    </>}>
      <p className="muted" style={{ margin: 0 }}>{message}</p>
    </Modal>
  )
}

export function Drawer({ open, onClose, title, children, actions }) {
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && closeRef.current()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div className="overlay" style={{ zIndex: 65 }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.aside className="drawer" role="dialog" aria-modal="true" aria-label={title} initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', damping: 30, stiffness: 300 }}>
            <div className="drawer-head"><h3 style={{ margin: 0 }}>{title}</h3><div className="row">{actions}<Button variant="ghost" icon={X} aria-label="Close" onClick={onClose} /></div></div>
            <div className="drawer-body">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

export function FormError({ error }) {
  if (!error) return null
  return <div className="form-error" role="alert">{error.message || String(error)}</div>
}
