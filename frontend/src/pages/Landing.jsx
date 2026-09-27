import { motion, useReducedMotion, useScroll, useSpring, useTransform } from 'framer-motion'
import {
  ArrowRight, Bell, Bot, BrainCircuit, CalendarClock, FileScan, FileSpreadsheet, FlaskConical, Gauge, Goal, LockKeyhole, ScanText, ShieldCheck, Sparkles, Upload, Wallet,
} from 'lucide-react'
import { Suspense, lazy, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Logo from '../components/Logo'
import { Parallax, Reveal, ScrollProgress, Stagger, Tilt, staggerItem } from '../components/motion'
import { Button } from '../components/ui'
import { api } from '../lib/api'
import { BRAND } from '../lib/brand'

const Hero3D = lazy(() => import('../components/Hero3D'))

const FEATURES = [
  { icon: Upload, title: 'Import any statement', text: 'CSV, Excel, PDF (even password-protected or scanned), Word, OFX, JSON, photos. Duplicates are caught before saving.' },
  { icon: BrainCircuit, title: 'AI that learns you', text: 'An on-device ML model categorises transactions and improves every time you correct it. No cloud, no cost.' },
  { icon: ScanText, title: 'Reads bank narrations', text: '“UPI/DR/4251…/SWIGGY/…@ybl” becomes Swiggy · UPI · Food delivery, with the reference and UPI id extracted.' },
  { icon: Gauge, title: 'Budgets that warn early', text: 'Monthly, weekly or custom budgets with pace tracking and alerts at the thresholds you choose.' },
  { icon: Bell, title: 'Smart alerts', text: 'Bills due, low balance, large or unusual payments, subscription price changes – in-app, email and browser push.' },
  { icon: Bot, title: 'Ask your money', text: '“How much did I spend on restaurants last month?” Answers come from your ledger, optionally phrased by a local open-source LLM.' },
  { icon: CalendarClock, title: 'Bills & subscriptions', text: 'Never miss a due date. Recurring charges are detected from your history automatically.' },
  { icon: Goal, title: 'Goals & net worth', text: 'Track savings goals, investments and loans, with month-by-month net worth history.' },
]

const STEPS = [
  { icon: FileSpreadsheet, title: 'Bring your data', text: 'Upload a statement, paste a bank SMS, or add expenses in two taps.' },
  { icon: Sparkles, title: 'It organises itself', text: 'Merchants, payment modes and categories are filled in – you just review.' },
  { icon: Gauge, title: 'See where it goes', text: 'Dashboards, budgets and insights update instantly from one source of truth.' },
  { icon: Bell, title: 'Get nudged in time', text: 'Alerts reach you before a bill is due or a budget runs out.' },
]

export default function Landing({ onSignedIn }) {
  const reduce = useReducedMotion()
  const heroRef = useRef(null)
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] })
  const progress = useSpring(scrollYProgress, { stiffness: 80, damping: 20 })
  const heroY = useTransform(scrollYProgress, [0, 1], reduce ? [0, 0] : [0, 160])
  const heroOpacity = useTransform(scrollYProgress, [0, 0.8], [1, reduce ? 1 : 0])
  const canvasScale = useTransform(scrollYProgress, [0, 1], reduce ? [1, 1] : [1, 1.25])
  const [busy, setBusy] = useState(false)

  const demo = async () => {
    setBusy(true)
    try { onSignedIn(await api.post('/auth/demo')) } finally { setBusy(false) }
  }

  return (
    <div className="landing">
      <ScrollProgress />
      <header className="landing-nav">
        <Link to="/" className="brand" style={{ padding: 0, color: 'var(--text)' }}><Logo size={32} />{BRAND.name}</Link>
        <nav className="row">
          <a href="#features" className="hide-mobile nav-anchor">Features</a>
          <a href="#privacy" className="hide-mobile nav-anchor">Privacy</a>
          <Link to="/login" className="btn ghost">Sign in</Link>
          <Link to="/register" className="btn primary">Get started</Link>
        </nav>
      </header>

      <section className="landing-hero" ref={heroRef}>
        <motion.div className="landing-canvas" style={{ scale: canvasScale }}>
          <Suspense fallback={null}><Hero3D className="landing-3d" progress={progress} /></Suspense>
        </motion.div>
        <motion.div className="landing-copy" style={{ y: heroY, opacity: heroOpacity }}>
          <motion.div className="pill" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <Sparkles size={14} /> {BRAND.meaning} · by {BRAND.owner}
          </motion.div>
          <motion.h1 initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.7 }}>
            Every rupee,<br /><span className="gradient-text">accounted for.</span>
          </motion.h1>
          <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }}>
            {BRAND.name} turns bank statements and UPI chaos into clear budgets, bills, goals and alerts – with AI that runs on your own computer.
          </motion.p>
          <motion.div className="row wrap" style={{ justifyContent: 'center', gap: 12 }} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.55 }}>
            <Link to="/register" className="btn primary lg">Create free account <ArrowRight size={17} /></Link>
            <Button className="lg" icon={FlaskConical} loading={busy} onClick={demo}>Explore the demo</Button>
          </motion.div>
          <div className="scroll-hint" aria-hidden><span /></div>
        </motion.div>
      </section>

      <section className="landing-preview">
        <Parallax offset={50}>
          <Tilt className="preview-window" max={6}>
            <div className="preview-bar"><i /><i /><i /><span>Sample preview – demo data</span></div>
            <div className="preview-grid">
              {[['Balance', '₹2,46,689', 'var(--accent)'], ['Spent this month', '₹48,687', 'var(--expense)'], ['Saved', '₹46,313', 'var(--income)'], ['Budget left', '₹11,313', 'var(--violet)']].map(([label, value, color], i) => (
                <motion.div key={label} className="preview-stat" style={{ '--c': color }} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: 0.1 * i }}>
                  <span>{label}</span><strong>{value}</strong>
                </motion.div>
              ))}
              <div className="preview-chart">
                {[38, 62, 45, 80, 55, 92, 70, 58, 86, 64, 74, 50].map((h, i) => (
                  <motion.i key={i} initial={{ height: 0 }} whileInView={{ height: `${h}%` }} viewport={{ once: true }} transition={{ delay: 0.05 * i, duration: 0.6 }} />
                ))}
              </div>
              <div className="preview-list">
                {[['Swiggy', 'Food delivery · UPI', '−₹533'], ['Salary – Acme', 'Salary · NEFT', '+₹95,000'], ['Netflix', 'Streaming · Card', '−₹649']].map(([a, b, c]) => (
                  <div key={a}><strong>{a}</strong><span>{b}</span><em className={c.startsWith('+') ? 'income' : ''}>{c}</em></div>
                ))}
              </div>
            </div>
          </Tilt>
        </Parallax>
      </section>

      <section className="landing-section">
        <Reveal><div className="kicker">How it works</div><h2>From statement to insight in minutes</h2></Reveal>
        <Stagger className="steps-grid">
          {STEPS.map((s, i) => (
            <motion.div key={s.title} variants={staggerItem} className="step-card">
              <span className="step-num">{i + 1}</span>
              <s.icon size={22} className="step-icon" />
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </motion.div>
          ))}
        </Stagger>
      </section>

      <section className="landing-section" id="features">
        <Reveal><div className="kicker">Everything in one place</div><h2>A real finance app, not a spreadsheet</h2></Reveal>
        <Stagger className="feature-grid">
          {FEATURES.map((f) => (
            <motion.div key={f.title} variants={staggerItem}>
              <Tilt className="feature-card" max={7}>
                <span className="feature-icon"><f.icon size={20} /></span>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </Tilt>
            </motion.div>
          ))}
        </Stagger>
      </section>

      <section className="landing-section formats">
        <Reveal><div className="kicker">Import</div><h2>Works with what your bank gives you</h2></Reveal>
        <div className="marquee" aria-label="Supported formats">
          <div className="marquee-track">
            {[...Array(2)].flatMap((_, k) => ['CSV', 'Excel XLSX', 'Old XLS', 'PDF', 'Password PDF', 'Scanned PDF (OCR)', 'Word DOCX', 'OFX / QFX', 'JSON', 'Photo of statement', 'Bank SMS', 'HDFC', 'SBI', 'ICICI', 'Axis', 'Kotak'].map((t) => (
              <span key={`${k}-${t}`} className="chip"><FileScan size={14} />{t}</span>
            )))}
          </div>
        </div>
      </section>

      <section className="landing-section" id="privacy">
        <div className="privacy">
          <Reveal className="privacy-copy">
            <div className="kicker">Private by design</div>
            <h2>Your money data never leaves your machine</h2>
            <ul>
              <li><ShieldCheck size={18} />Runs locally – database, AI model and OCR all on your PC.</li>
              <li><LockKeyhole size={18} />Passwords hashed with scrypt, sessions in HttpOnly cookies, CSRF protection.</li>
              <li><Wallet size={18} />Free and open source. No subscriptions, no ads, no data selling.</li>
            </ul>
          </Reveal>
          <Reveal delay={0.15}>
            <Tilt className="privacy-card" max={10}><Logo size={120} /><strong>{BRAND.name}</strong><span>{BRAND.meaning}</span></Tilt>
          </Reveal>
        </div>
      </section>

      <section className="landing-cta">
        <Reveal>
          <h2>Start your {BRAND.name.toLowerCase()} today.</h2>
          <div className="row wrap" style={{ justifyContent: 'center', gap: 12 }}>
            <Link to="/register" className="btn primary lg">Create free account <ArrowRight size={17} /></Link>
            <Link to="/login" className="btn lg">Sign in</Link>
          </div>
        </Reveal>
      </section>
      <footer className="landing-footer">
        <span className="row"><Logo size={22} /> {BRAND.name} · made by {BRAND.owner}</span>
        <span className="faint">Open-source stack: FastAPI · React · scikit-learn · RapidOCR · Three.js</span>
      </footer>
    </div>
  )
}
