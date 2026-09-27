import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Bot, Cpu, SendHorizonal, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Button, Card, PageHead } from '../components/ui'
import { api } from '../lib/api'

const SUGGESTED = [
  'Where did I spend the most this month?',
  'How much did I spend on food delivery last month?',
  'Compare last month and this month',
  'Which category increased the most?',
  'Which subscriptions cost the most?',
  'How much did I earn this month?',
  'What was my largest expense this month?',
  'How are my budgets doing?',
  'What is my net worth?',
]

function DataTable({ data }) {
  if (!data) return null
  const list = Object.entries(data).find(([, v]) => Array.isArray(v) && v.length && typeof v[0] === 'object')
  if (!list) return null
  const [name, rows] = list
  const cols = Object.keys(rows[0]).filter((c) => !c.startsWith('_'))
  return (
    <details style={{ marginTop: 8 }}>
      <summary className="faint" style={{ fontSize: 12, cursor: 'pointer' }}>Show {name.replace(/_/g, ' ')} ({rows.length})</summary>
      <div className="table-wrap" style={{ margin: '6px 0 0', padding: 0 }}>
        <table className="table" style={{ fontSize: 13 }}>
          <thead><tr>{cols.map((c) => <th key={c}>{c.replace(/_/g, ' ')}</th>)}</tr></thead>
          <tbody>{rows.slice(0, 12).map((r, i) => <tr key={i}>{cols.map((c) => <td key={c}>{String(r[c] ?? '')}</td>)}</tr>)}</tbody>
        </table>
      </div>
    </details>
  )
}

export default function Assistant() {
  const status = useQuery({ queryKey: ['ai-status'], queryFn: () => api.get('/ai/status'), staleTime: 30_000 })
  const [messages, setMessages] = useState([])
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages, busy])

  async function ask(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setQ('')
    setMessages((m) => [...m, { role: 'me', text }])
    setBusy(true)
    try {
      const r = await api.post('/ai/ask', { question: text })
      setMessages((m) => [...m, { role: 'bot', text: r.answer, engine: r.engine, data: r.data, tools: r.tools_used }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'bot', text: e.message, engine: 'error' }])
    } finally {
      setBusy(false)
    }
  }

  const llm = status.data?.llm
  return (
    <>
      <PageHead kicker="AI" title="Ask your money">
        Questions are answered from your own ledger. Numbers are always computed by the app – a local AI model (optional) only helps understand the question and phrase the answer.
      </PageHead>
      <div className="row wrap" style={{ marginBottom: 14, gap: 8 }}>
        <Badge tone="success"><Cpu size={12} /> Rules engine: on</Badge>
        {llm && (llm.available ? <Badge tone="violet"><Sparkles size={12} /> Local AI: {llm.model}</Badge>
          : <Badge><Bot size={12} /> Local AI: off – <Link to="/settings?section=ai" style={{ marginLeft: 3 }}>set up (free)</Link></Badge>)}
      </div>
      <Card>
        <div className="chat" aria-live="polite">
          {messages.length === 0 && (
            <div className="empty" style={{ padding: '20px 10px' }}>
              <div className="icon"><Bot size={26} /></div>
              <h3>What would you like to know?</h3>
              <div className="suggest-chips" style={{ justifyContent: 'center', marginTop: 14 }}>
                {SUGGESTED.map((s) => <button key={s} type="button" onClick={() => ask(s)}>{s}</button>)}
              </div>
            </div>
          )}
          <AnimatePresence initial={false}>
            {messages.map((m, i) => (
              <motion.div key={i} className={`bubble ${m.role}`} initial={{ opacity: 0, y: 10, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }}>
                {m.text}
                {m.role === 'bot' && m.engine !== 'error' && (
                  <>
                    <DataTable data={m.data} />
                    <div className="meta">{m.engine === 'llm' ? `Local AI${m.tools?.length ? ` · used ${m.tools.join(', ')}` : ''}` : 'Rules engine'} · figures from your ledger</div>
                  </>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
          {busy && <div className="bubble bot typing" aria-label="Thinking"><span /><span /><span /></div>}
          <div ref={end} />
        </div>
        <form className="row" style={{ marginTop: 14 }} onSubmit={(e) => { e.preventDefault(); ask() }}>
          <input className="input grow" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. How much did I spend on Swiggy in August?" aria-label="Question" maxLength={500} />
          <Button type="submit" variant="primary" icon={SendHorizonal} loading={busy} disabled={!q.trim()}>Ask</Button>
        </form>
        {messages.length > 0 && (
          <div className="suggest-chips" style={{ marginTop: 10 }}>
            {SUGGESTED.slice(0, 5).map((s) => <button key={s} type="button" onClick={() => ask(s)}>{s}</button>)}
          </div>
        )}
      </Card>
    </>
  )
}
