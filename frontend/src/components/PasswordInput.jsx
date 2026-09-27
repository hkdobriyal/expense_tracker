import { Eye, EyeOff } from 'lucide-react'
import { forwardRef, useState } from 'react'

// Mirrors the server rule: ≥10 characters, upper + lower case, a digit.
export function passwordChecks(value = '') {
  return [
    { label: '10+ characters', ok: value.length >= 10 },
    { label: 'upper & lower case', ok: /[a-z]/.test(value) && /[A-Z]/.test(value) },
    { label: 'a number', ok: /\d/.test(value) },
    { label: 'a symbol (bonus)', ok: /[^A-Za-z0-9]/.test(value), optional: true },
  ]
}

export function passwordScore(value = '') {
  const checks = passwordChecks(value)
  let score = checks.filter((c) => c.ok).length
  if (value.length >= 14) score += 1
  return Math.min(score, 5)
}

const PasswordInput = forwardRef(function PasswordInput({ value, onChange, showStrength = false, autoComplete = 'current-password', id, ...props }, ref) {
  const [visible, setVisible] = useState(false)
  const score = passwordScore(value)
  const labels = ['Too weak', 'Weak', 'Fair', 'Good', 'Strong', 'Excellent']
  const tone = score <= 1 ? 'var(--critical)' : score <= 2 ? 'var(--warning)' : score <= 3 ? 'var(--accent)' : 'var(--success)'
  return (
    <div>
      <div className="password-field">
        <input ref={ref} id={id} className="input" type={visible ? 'text' : 'password'} value={value} onChange={onChange} autoComplete={autoComplete} spellCheck={false} {...props} />
        <button type="button" className="eye" onClick={() => setVisible((v) => !v)} aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible} tabIndex={0}>
          {visible ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
      {showStrength && value && (
        <div className="strength" aria-live="polite">
          <div className="strength-bar"><div style={{ width: `${(score / 5) * 100}%`, background: tone }} /></div>
          <div className="row wrap" style={{ gap: 10, fontSize: 12, marginTop: 6 }}>
            <strong style={{ color: tone }}>{labels[score]}</strong>
            {passwordChecks(value).map((c) => <span key={c.label} className={c.ok ? 'income' : 'faint'}>{c.ok ? '✓' : '○'} {c.label}</span>)}
          </div>
        </div>
      )}
    </div>
  )
})

export default PasswordInput
