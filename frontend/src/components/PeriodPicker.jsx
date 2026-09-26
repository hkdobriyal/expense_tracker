import { useState } from 'react'
import { Segmented } from './ui'

export const PRESETS = [
  { value: 'this_month', label: 'Month' },
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '3m', label: '3M' },
  { value: '6m', label: '6M' },
  { value: '1y', label: '1Y' },
  { value: 'custom', label: 'Custom' },
]

// value: { preset, start, end }  →  query params for the API
export function periodParams(value) {
  return value.preset === 'custom' ? { preset: 'custom', start: value.start, end: value.end } : { preset: value.preset }
}

export function usePeriod(initial = 'this_month') {
  return useState({ preset: initial, start: '', end: '' })
}

export default function PeriodPicker({ value, onChange, presets = PRESETS }) {
  return (
    <div className="row wrap">
      <Segmented label="Period" value={value.preset} onChange={(preset) => onChange({ ...value, preset })} options={presets} />
      {value.preset === 'custom' && (
        <>
          <input className="input" type="date" aria-label="From" style={{ width: 'auto' }} value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />
          <input className="input" type="date" aria-label="To" style={{ width: 'auto' }} value={value.end} onChange={(e) => onChange({ ...value, end: e.target.value })} />
        </>
      )}
    </div>
  )
}

export function periodReady(value) {
  return value.preset !== 'custom' || (value.start && value.end && value.start <= value.end)
}
