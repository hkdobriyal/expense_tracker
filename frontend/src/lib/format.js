// Formatting helpers. Amounts arrive from the API as integer minor units (paise);
// they are only divided for display, never used for arithmetic here.

const EXPONENT = { JPY: 0, KRW: 0, BHD: 3, KWD: 3, OMR: 3 }
const formatters = new Map()

export function exponent(currency = 'INR') {
  return EXPONENT[currency] ?? 2
}

export function money(minor, currency = 'INR', { compact = false, decimals, sign = false } = {}) {
  if (minor === null || minor === undefined) return '—'
  const exp = exponent(currency)
  const value = Number(minor) / 10 ** exp
  const digits = decimals ?? (compact ? 0 : Number.isInteger(value) ? 0 : exp)
  const key = `${currency}|${compact}|${digits}`
  if (!formatters.has(key)) {
    formatters.set(key, new Intl.NumberFormat('en-IN', {
      style: 'currency', currency, notation: compact ? 'compact' : 'standard',
      minimumFractionDigits: digits, maximumFractionDigits: compact ? 1 : digits,
    }))
  }
  const text = formatters.get(key).format(value)
  return sign && value > 0 ? `+${text}` : text
}

// "1234.50" (string) for form inputs, from minor units – exact, via string math.
export function toInput(minor, currency = 'INR') {
  if (minor === null || minor === undefined) return ''
  const exp = exponent(currency)
  const negative = minor < 0
  const digits = String(Math.abs(minor)).padStart(exp + 1, '0')
  const whole = exp ? digits.slice(0, -exp) : digits
  const frac = exp ? digits.slice(-exp) : ''
  return `${negative ? '-' : ''}${whole}${frac && Number(frac) ? `.${frac}` : ''}`
}

export function pct(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return `${Number(value).toFixed(digits)}%`
}

export function todayISO() {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

export function shortDate(value) {
  if (!value) return ''
  return new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

export function longDate(value) {
  if (!value) return ''
  return new Date(`${String(value).slice(0, 10)}T00:00:00`).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function monthLabel(value) {
  return new Date(`${String(value).slice(0, 7)}-01T00:00:00`).toLocaleDateString('en-IN', { month: 'short', year: '2-digit' })
}

export function relativeTime(value) {
  if (!value) return 'never'
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return longDate(value)
}

export function daysUntil(value) {
  const due = new Date(`${String(value).slice(0, 10)}T00:00:00`)
  const today = new Date(`${todayISO()}T00:00:00`)
  return Math.round((due - today) / 86400000)
}

export const TYPE_LABEL = { expense: 'Expense', income: 'Income', transfer: 'Transfer', refund: 'Refund', adjustment: 'Adjustment', investment: 'Investment' }
export const ACCOUNT_LABEL = {
  current: 'Current', savings: 'Savings', credit_card: 'Credit card', cash: 'Cash', wallet: 'Wallet', investment: 'Investment',
  loan: 'Loan', mortgage: 'Mortgage', asset: 'Asset', liability: 'Liability',
}
export const FREQ_LABEL = { once: 'One-off', weekly: 'Weekly', monthly: 'Monthly', quarterly: 'Quarterly', half_yearly: 'Half-yearly', yearly: 'Yearly' }

// Signed display amount for a transaction row (from the account's perspective).
export function signedAmount(txn) {
  if (txn.type === 'income' || txn.type === 'refund') return txn.amount_minor
  if (txn.type === 'adjustment') return txn.amount_minor
  return -txn.amount_minor
}
