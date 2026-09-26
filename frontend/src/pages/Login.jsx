import { useQuery } from '@tanstack/react-query'
import { FlaskConical, LockKeyhole, PiggyBank } from 'lucide-react'
import { Suspense, lazy, useState } from 'react'
import { Button, Field, FormError, Select } from '../components/ui'
import { api } from '../lib/api'

const Hero3D = lazy(() => import('../components/Hero3D'))

const CURRENCIES = ['INR', 'EUR', 'USD', 'GBP', 'AED', 'SGD', 'AUD', 'CAD']

export default function Login({ onSignedIn, apiError }) {
  const status = useQuery({ queryKey: ['auth-status'], queryFn: () => api.get('/auth/status'), retry: false })
  const firstRun = status.data && !status.data.has_account
  const [form, setForm] = useState({ email: '', password: '', display_name: '', base_currency: 'INR' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState('')

  async function submit(e) {
    e.preventDefault()
    setError(null)
    setBusy('auth')
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata'
      const data = firstRun
        ? await api.post('/auth/register', { ...form, timezone: tz })
        : await api.post('/auth/login', { email: form.email, password: form.password })
      onSignedIn(data)
    } catch (err) {
      setError(err)
    } finally {
      setBusy('')
    }
  }

  async function demo() {
    setError(null)
    setBusy('demo')
    try {
      onSignedIn(await api.post('/auth/demo'))
    } catch (err) {
      setError(err)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="auth">
      <section className="auth-art">
        <Suspense fallback={null}><Hero3D className="auth-canvas" /></Suspense>
        <div className="brand" style={{ position: 'relative' }}><span className="brand-mark"><PiggyBank size={18} /></span>ledgerly</div>
        <div style={{ position: 'relative' }}>
          <h1>Every rupee, <em>accounted for.</em></h1>
          <p className="muted" style={{ maxWidth: 460, fontSize: 16 }}>Budgets, bills, subscriptions, goals, net worth and smart alerts – running on your own machine, with your data outside the cloud.</p>
        </div>
        <div className="row faint" style={{ position: 'relative', fontSize: 13 }}><LockKeyhole size={15} /> Local-first · open source stack · no paid services required</div>
      </section>
      <section className="auth-form">
        <div className="card">
          <div className="kicker">{firstRun ? 'First run' : 'Welcome back'}</div>
          <h2 style={{ margin: '6px 0 4px', letterSpacing: '-0.03em' }}>{firstRun ? 'Create your workspace' : 'Sign in'}</h2>
          <p className="muted" style={{ marginTop: 0, fontSize: 14 }}>{firstRun ? 'This installation is single-user: the first account becomes the owner.' : 'Use the account you created on this installation.'}</p>
          {apiError && <FormError error={apiError} />}
          <form className="stack" onSubmit={submit}>
            {firstRun && <Field label="Your name"><input className="input" autoComplete="name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} /></Field>}
            <Field label="Email" required><input className="input" type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Password" required hint={firstRun ? 'At least 10 characters with upper- and lower-case letters and a number.' : undefined}>
              <input className="input" type="password" required minLength={firstRun ? 10 : undefined} autoComplete={firstRun ? 'new-password' : 'current-password'} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
            {firstRun && (
              <Field label="Base currency" hint="All totals are reported in this currency. It cannot change once transactions exist.">
                <Select value={form.base_currency} onChange={(e) => setForm({ ...form, base_currency: e.target.value })} options={CURRENCIES.map((c) => ({ value: c, label: c }))} />
              </Field>
            )}
            <FormError error={error} />
            <Button type="submit" variant="primary" loading={busy === 'auth'} disabled={!status.data}>{firstRun ? 'Create account' : 'Sign in'}</Button>
          </form>
          <div className="row" style={{ margin: '18px 0 10px' }}><div className="grow" style={{ height: 1, background: 'var(--border)' }} /><span className="faint" style={{ fontSize: 12 }}>or</span><div className="grow" style={{ height: 1, background: 'var(--border)' }} /></div>
          <Button icon={FlaskConical} style={{ width: '100%' }} loading={busy === 'demo'} onClick={demo}>Try the demo workspace</Button>
          <p className="faint" style={{ fontSize: 12, marginBottom: 0 }}>The demo uses sample data from a sandbox bank in a separate, isolated workspace. It never touches your real data.</p>
        </div>
      </section>
    </div>
  )
}
