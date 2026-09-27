import { useId } from 'react'

// Same mark as public/icon.svg, inline so it inherits no extra requests.
export default function Logo({ size = 32 }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" aria-hidden="true" style={{ flexShrink: 0, filter: 'drop-shadow(0 8px 18px rgba(138,230,255,.28))' }}>
      <defs>
        <linearGradient id={`g${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8ae6ff" /><stop offset="0.55" stopColor="#8d7bff" /><stop offset="1" stopColor="#b29bff" />
        </linearGradient>
      </defs>
      <rect width="512" height="512" rx="120" fill={`url(#g${id})`} />
      <g fill="none" stroke="#06202f" strokeWidth="40" strokeLinecap="round" strokeLinejoin="round">
        <path d="M150 150 H362" /><path d="M150 228 H362" />
        <path d="M190 150 C300 150 322 188 322 214 C322 262 276 290 206 290 H176 L332 392" />
      </g>
      <circle cx="392" cy="120" r="26" fill="#7ef0c2" />
    </svg>
  )
}
