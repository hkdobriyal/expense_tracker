import { categories, colors } from './constants'

export function money(value) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value || 0)
}

export function shortDate(value) {
  if (!value) return 'Today'
  return new Date(value).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })
}

export function longDate(value = new Date()) {
  return new Date(value).toLocaleDateString('en-IN', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).toUpperCase()
}

export function monthKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return monthKey(new Date())
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(key) {
  const [year, month] = String(key).split('-')
  const date = new Date(Number(year), Number(month) - 1, 1)
  return date.toLocaleDateString('en-IN', { month: 'short', year: 'numeric' })
}

export function categoryColor(category) {
  const index = categories.indexOf(category)
  return colors[index] || colors[colors.length - 1]
}

export function daysUntil(value) {
  if (!value) return null
  const due = new Date(value)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  due.setHours(0, 0, 0, 0)
  return Math.round((due - today) / 86400000)
}

export function inMonth(value, key) {
  if (!value || key === 'all') return true
  return String(value).slice(0, 7) === key
}

export function lastMonths(count = 8) {
  const now = new Date()
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(now.getFullYear(), now.getMonth() - (count - 1 - index), 1)
    return monthKey(date)
  })
}
