import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ArrowLeft, CheckCircle2, FlaskConical, LockKeyhole, MailCheck, MailWarning } from 'lucide-react'
import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Logo from '../components/Logo'
import PasswordInput, { passwordChecks } from '../components/PasswordInput'
import { Button, Field, FormError, Select } from '../components/ui'
import { api } from '../lib/api'
import { BRAND } from '../lib/brand'

const Hero3D = lazy(() => import('../components/Hero3D'))
const CURRENCIES = ['INR', 'EUR', 'USD', 'GBP', 'AED', 'SGD', 'AUD', 'CAD']

export function useAuthStatus() {
  return useQuery({ queryKey: ['auth-status'], queryFn: () => api.get('/auth/status'), retry: false, staleTime: 30_000 })
}

function AuthShell({ title, kicker, subtitle, children, footer }) {
  return (
    <div className="auth">
      <section className="auth-art">
        <Suspense fallback={null}><Hero3D className="auth-canvas" /></Suspense>
        <Link to="/" className="brand" style={{ position: 'relative', color: 'var(--text)' }}><Logo size={34} />{BRAND.name}</Link>
        <motion.div className="auth-copy" style={{ position: 'relative', zIndex: 1 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
          <h1>Every rupee, <em>accounted for.</em></h1>
          <p className="muted" style={{ maxWidth: 460, fontSize: 16 }}>Budgets, bills, subscriptions, goals, AI categorisation and smart alerts – running on your own machine.</p>
        </motion.div>
        <div className="row faint" style={{ position: 'relative', fontSize: 13 }}><LockKeyhole size={15} /> Local-first · open source · by {BRAND.owner}</div>
      </section>
      <section className="auth-form">
        <motion.div className="card" initial={{ opacity: 0, y: 16, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} transition={{ type: 'spring', damping: 22 }}>
          <Link to="/" className="brand show-mobile" style={{ padding: '0 0 16px', color: 'var(--text)' }}><Logo size={30} />{BRAND.name}</Link>
          {kicker && <div className="kicker">{kicker}</div>}
          <h2 style={{ margin: '6px 0 4px', letterSpacing: '-0.03em' }}>{title}</h2>
          {subtitle && <p className="muted" style={{ marginTop: 0, fontSize: 14 }}>{subtitle}</p>}
          {children}
          {footer && <div className="auth-footer">{footer}</div>}
        </motion.div>
      </section>
    </div>
  )
}

function DemoButton({ onSignedIn }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  return (
    <>
      <div className="row" style={{ margin: '18px 0 10px' }}><div className="grow divider" /><span className="faint" style={{ fontSize: 12 }}>or</span><div className="grow divider" /></div>
      <Button icon={FlaskConical} style={{ width: '100%' }} loading={busy} onClick={async () => {
        setBusy(true); setError(null)
        try { onSignedIn(await api.post('/auth/demo')) } catch (e) { setError(e) } finally { setBusy(false) }
      }}>Try the demo workspace</Button>
      <FormError error={error} />
    </>
  )
}

export function Login({ onSignedIn }) {
  const status = useAuthStatus()
  const [form, setForm] = useState({ email: '', password: '', remember: true })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const firstRun = status.data && !status.data.has_account
  async function submit(e) {
    e.preventDefault()
    setError(null); setBusy(true)
    try { onSignedIn(await api.post('/auth/login', form)) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return (
    <AuthShell kicker="Welcome back" title="Sign in" subtitle={firstRun ? 'No account exists yet on this installation.' : `Sign in to ${BRAND.name}.`}
      footer={status.data?.registration_open && <>New here? <Link to="/register">Create an account</Link></>}>
      <form className="stack" onSubmit={submit}>
        <Field label="Email" required><input className="input" type="email" required autoComplete="email" autoFocus value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Password" required><PasswordInput required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
        <div className="row between">
          <label className="checkbox" style={{ fontSize: 13 }}><input type="checkbox" checked={form.remember} onChange={(e) => setForm({ ...form, remember: e.target.checked })} />Remember me</label>
          <Link to="/forgot-password" style={{ fontSize: 13, fontWeight: 600 }}>Forgot password?</Link>
        </div>
        <FormError error={error} />
        <Button type="submit" variant="primary" loading={busy}>Sign in</Button>
      </form>
      <DemoButton onSignedIn={onSignedIn} />
    </AuthShell>
  )
}

export function Register({ onSignedIn }) {
  const status = useAuthStatus()
  const [form, setForm] = useState({ display_name: '', email: '', password: '', confirm: '', base_currency: 'INR' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const ready = passwordChecks(form.password).filter((c) => !c.optional).every((c) => c.ok)
  async function submit(e) {
    e.preventDefault()
    setError(null)
    if (form.password !== form.confirm) return setError(new Error('The two passwords don’t match'))
    setBusy(true)
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
      onSignedIn(await api.post('/auth/register', { display_name: form.display_name, email: form.email, password: form.password, base_currency: form.base_currency, timezone: tz }))
    } catch (err) { setError(err) } finally { setBusy(false) }
  }
  if (status.data && !status.data.registration_open) {
    return <AuthShell title="Registration is closed" subtitle="Ask the owner of this installation for an account." footer={<Link to="/login">Back to sign in</Link>} />
  }
  return (
    <AuthShell kicker="Get started" title="Create your account" subtitle="Free, private, and your data stays on this machine."
      footer={<>Already have an account? <Link to="/login">Sign in</Link></>}>
      <form className="stack" onSubmit={submit}>
        <Field label="Your name"><input className="input" autoComplete="name" autoFocus value={form.display_name} placeholder="Hemant Kumar" onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>
        <Field label="Email" required><input className="input" type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
        <Field label="Password" required><PasswordInput required showStrength autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
        <Field label="Confirm password" required><PasswordInput required autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} aria-invalid={form.confirm && form.confirm !== form.password ? 'true' : undefined} /></Field>
        <Field label="Base currency" hint="All totals are reported in this currency. Fixed once you add transactions.">
          <Select value={form.base_currency} onChange={(e) => setForm({ ...form, base_currency: e.target.value })} options={CURRENCIES.map((c) => ({ value: c, label: c }))} />
        </Field>
        <FormError error={error} />
        <Button type="submit" variant="primary" loading={busy} disabled={!ready || !form.email}>Create account</Button>
      </form>
      <DemoButton onSignedIn={onSignedIn} />
    </AuthShell>
  )
}

export function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    setError(null); setBusy(true)
    try { setResult(await api.post('/auth/forgot-password', { email })) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  return (
    <AuthShell kicker="Account recovery" title="Forgot your password?" subtitle="Enter your email and we’ll send a reset link (valid for 30 minutes)."
      footer={<Link to="/login" className="row" style={{ gap: 6 }}><ArrowLeft size={14} />Back to sign in</Link>}>
      {result ? (
        <div className="stack">
          <div className="notice success"><MailCheck size={18} /><div><strong>Check your inbox</strong>{result.message}</div></div>
          {!result.email_configured && (
            <div className="notice warning"><MailWarning size={18} /><div><strong>Email isn’t set up on this server yet</strong>
              The reset link was written to the API console window instead. Add your SMTP details to <code>backend/.env</code> to receive real emails.</div></div>
          )}
        </div>
      ) : (
        <form className="stack" onSubmit={submit}>
          <Field label="Email" required><input className="input" type="email" required autoFocus autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
          <FormError error={error} />
          <Button type="submit" variant="primary" loading={busy}>Send reset link</Button>
        </form>
      )}
    </AuthShell>
  )
}

export function ResetPassword() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') || ''
  const [form, setForm] = useState({ password: '', confirm: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const ready = passwordChecks(form.password).filter((c) => !c.optional).every((c) => c.ok) && form.password === form.confirm
  async function submit(e) {
    e.preventDefault()
    setError(null); setBusy(true)
    try { await api.post('/auth/reset-password', { token, password: form.password }); setDone(true) } catch (err) { setError(err) } finally { setBusy(false) }
  }
  if (!token) return <AuthShell title="Invalid link" subtitle="This reset link is incomplete." footer={<Link to="/forgot-password">Request a new link</Link>} />
  return (
    <AuthShell kicker="Account recovery" title={done ? 'Password updated' : 'Choose a new password'}>
      {done ? (
        <div className="stack">
          <div className="notice success"><CheckCircle2 size={18} /><div><strong>All set</strong>For your security, every device was signed out. Sign in with your new password.</div></div>
          <Button variant="primary" onClick={() => navigate('/login')}>Sign in</Button>
        </div>
      ) : (
        <form className="stack" onSubmit={submit}>
          <Field label="New password" required><PasswordInput required autoFocus showStrength autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>
          <Field label="Confirm new password" required><PasswordInput required autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} /></Field>
          <FormError error={error} />
          <Button type="submit" variant="primary" loading={busy} disabled={!ready}>Update password</Button>
          {error?.status === 400 && <Link to="/forgot-password">Request a new link</Link>}
        </form>
      )}
    </AuthShell>
  )
}

export function VerifyEmail({ signedIn }) {
  const [params] = useSearchParams()
  const [state, setState] = useState({ status: 'working' })
  const started = useRef(false)
  useEffect(() => {
    if (started.current) return
    started.current = true
    api.post('/auth/verify-email', { token: params.get('token') || '' })
      .then((r) => setState({ status: 'ok', email: r.email }))
      .catch((e) => setState({ status: 'error', message: e.message }))
  }, [params])
  return (
    <AuthShell title={state.status === 'ok' ? 'Email confirmed' : state.status === 'error' ? 'Link not valid' : 'Confirming…'}
      footer={<Link to={signedIn ? '/' : '/login'}>{signedIn ? 'Go to dashboard' : 'Sign in'}</Link>}>
      {state.status === 'ok' && <div className="notice success"><CheckCircle2 size={18} /><div><strong>{state.email}</strong>You’ll now receive alerts and password resets here.</div></div>}
      {state.status === 'error' && <div className="notice critical"><div>{state.message} You can request a new one from Settings → Security.</div></div>}
    </AuthShell>
  )
}
