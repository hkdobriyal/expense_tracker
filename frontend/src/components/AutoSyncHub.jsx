import React, { useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { parseSMSText, syncSMSWebhook, importBatchTransactions } from '../lib/api'
import { money, shortDate } from '../lib/format'
import { playChime, playClick, playCoin } from '../lib/sound'

const SAMPLE_PRESETS = [
  {
    id: 'swiggy',
    icon: '🍔',
    label: 'Swiggy UPI',
    desc: 'Dinner delivery',
    amount: '₹340.00',
    sms: 'Dear HDFC Bank User, INR 340.00 debited from a/c **1234 to SWIGGY on 13-09-26 via UPI txn 42516781290. Bal: INR 34,210.00',
  },
  {
    id: 'salary',
    icon: '💼',
    label: 'Salary Inflow',
    desc: 'Monthly payroll',
    amount: '+₹85,000.00',
    sms: 'Dear Customer, your ICICI Bank Acct XX901 is credited with INR 85,000.00 on 01-Sep-26 towards Salary. Clear Bal is INR 1,12,400.00',
  },
  {
    id: 'zepto',
    icon: '🛒',
    label: 'Zepto Groceries',
    desc: '10-min groceries',
    amount: '₹180.00',
    sms: 'Dear SBI User, A/C ...5678 debited by 180.0 on 12Sep26 trf to Zepto UPI: 491823719283. Avl Bal: Rs 14,350',
  },
  {
    id: 'zerodha',
    icon: '📈',
    label: 'Zerodha SIP',
    desc: 'Nifty Index SIP',
    amount: '₹10,000.00',
    sms: 'Axis Bank: Rs 10000.00 debited from A/c no. XX345 on 10-09-26 towards Zerodha Broking. UPI Ref 41029384712',
  },
  {
    id: 'electricity',
    icon: '⚡',
    label: 'BESCOM Power',
    desc: 'Electricity bill',
    amount: '₹1,850.00',
    sms: 'Paid Rs. 1,850.00 to BESCOM Electricity on PhonePe. Txn ID: T26091312345678. Debited from Bank of Baroda a/c **8765',
  },
  {
    id: 'netflix',
    icon: '🎬',
    label: 'Netflix Plan',
    desc: 'Monthly 4K HDR',
    amount: '₹649.00',
    sms: 'Alert: Rs 649 debited from your HDFC card **3322 for NETFLIX on 05-Sep-26. Auto-debit successful.',
  },
]

export function AutoSyncHub({ onTransactionAdded, advancedAnalytics }) {
  const [activeTab, setActiveTab] = useState('simulate')
  const [smsInput, setSmsInput] = useState('')
  const [parsing, setParsing] = useState(false)
  const [parsedPreview, setParsedPreview] = useState(null)
  const [parseError, setParseError] = useState('')
  const [simulating, setSimulating] = useState('')
  const [csvFile, setCsvFile] = useState(null)
  const [csvPreview, setCsvPreview] = useState([])
  const [importing, setImporting] = useState(false)
  const [importSummary, setImportSummary] = useState(null)
  const fileInputRef = useRef(null)

  // 1. Live Simulator action
  async function triggerSimulation(preset) {
    try {
      playClick()
      setSimulating(preset.id)
      const res = await syncSMSWebhook(preset.sms)
      playChime()
      if (onTransactionAdded) {
        onTransactionAdded(res.data.transaction)
      }
    } catch (err) {
      console.error('Simulation error:', err)
    } finally {
      setTimeout(() => setSimulating(''), 700)
    }
  }

  // 2. Text Parser Action
  async function handleParseInput() {
    if (!smsInput.trim()) return
    try {
      playClick()
      setParsing(true)
      setParseError('')
      const res = await parseSMSText(smsInput)
      if (res.data.success && res.data.data) {
        setParsedPreview(res.data.data)
        playCoin()
      } else {
        setParseError(res.data.error || 'Could not parse text')
      }
    } catch {
      setParseError('Failed to contact parser API')
    } finally {
      setParsing(false)
    }
  }

  // 3. Confirm adding parsed transaction
  async function handleConfirmParsed() {
    if (!parsedPreview) return
    try {
      playClick()
      setParsing(true)
      const res = await syncSMSWebhook(parsedPreview.raw_text || smsInput)
      playChime()
      if (onTransactionAdded) {
        onTransactionAdded(res.data.transaction)
      }
      setParsedPreview(null)
      setSmsInput('')
    } catch (err) {
      setParseError('Failed to save parsed transaction')
    } finally {
      setParsing(false)
    }
  }

  // 4. Handle CSV upload
  function handleCsvUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setCsvFile(file)
    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target?.result
      if (typeof text !== 'string') return
      parseCsvData(text)
    }
    reader.readAsText(file)
  }

  function parseCsvData(content) {
    const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0)
    if (lines.length < 2) return

    const rows = []
    const headers = lines[0].split(',').map((h) => h.trim().toLowerCase().replace(/['"]+/g, ''))

    // Try finding date, title/description, amount, kind
    const dateIdx = headers.findIndex((h) => h.includes('date') || h.includes('time'))
    const titleIdx = headers.findIndex((h) => h.includes('title') || h.includes('desc') || h.includes('narration') || h.includes('merchant') || h.includes('particular'))
    const amountIdx = headers.findIndex((h) => h.includes('amount') || h.includes('inr') || h.includes('debit') || h.includes('val'))
    const kindIdx = headers.findIndex((h) => h.includes('kind') || h.includes('type'))

    for (let i = 1; i < Math.min(lines.length, 100); i++) {
      const cols = lines[i].split(',').map((c) => c.trim().replace(/^["']|["']$/g, ''))
      if (cols.length < 2) continue

      const title = cols[titleIdx >= 0 ? titleIdx : 1] || 'Bank Transaction'
      const rawAmt = cols[amountIdx >= 0 ? amountIdx : 2]?.replace(/[^0-9.-]/g, '') || '0'
      const amount = Math.abs(parseFloat(rawAmt)) || 0
      const date = cols[dateIdx >= 0 ? dateIdx : 0] || new Date().toISOString()
      const kind = (kindIdx >= 0 ? cols[kindIdx] : rawAmt.startsWith('-') ? 'expense' : 'expense').toLowerCase()

      if (amount > 0) {
        rows.push({
          title,
          amount,
          date: date.includes('T') ? date : `${date}T12:00:00`,
          kind: kind.includes('inc') || kind.includes('credit') ? 'income' : kind.includes('inv') ? 'investment' : 'expense',
          category: 'Other',
          payment_method: 'Bank transfer',
          recurring: false,
        })
      }
    }
    setCsvPreview(rows)
    playClick()
  }

  async function commitCsvImport() {
    if (!csvPreview.length) return
    try {
      setImporting(true)
      playClick()
      const res = await importBatchTransactions(csvPreview)
      playChime()
      setImportSummary(res.data)
      setCsvPreview([])
      setCsvFile(null)
      if (onTransactionAdded) onTransactionAdded()
    } catch {
      setParseError('Could not import statement batch')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="autosync-hub-view">
      {/* Header Banner */}
      <section className="autosync-hero panel">
        <div className="autosync-hero-text">
          <span className="section-kicker">AUTOMATION & CONNECTIVITY</span>
          <h1>Zero-Touch UPI & Bank Sync</h1>
          <p>
            Indian banks don't offer public consumer APIs, but Ledgerly gives you <strong>three working, effortless ways</strong> to reflect every UPI and bank debit automatically.
          </p>
        </div>

        {/* Financial Health Score & Quick Metrics */}
        {advancedAnalytics && (
          <div className="autosync-health-card">
            <div className="health-score-ring">
              <span className="score-num">{advancedAnalytics.financial_health_score || 75}</span>
              <span className="score-sub">HEALTH INDEX</span>
            </div>
            <div className="health-stats">
              <div>
                <span>DAILY BURN RATE</span>
                <strong>{money(advancedAnalytics.daily_burn_rate || 0)}/day</strong>
              </div>
              <div>
                <span>30-DAY OUTFLOW</span>
                <strong>{money(advancedAnalytics.last_30_days_expense || 0)}</strong>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Tabs */}
      <div className="autosync-tabs">
        <button className={activeTab === 'simulate' ? 'active' : ''} onClick={() => { playClick(); setActiveTab('simulate') }}>
          <span className="tab-icon">⚡</span> 1-Click Live Simulator
        </button>
        <button className={activeTab === 'smart-paste' ? 'active' : ''} onClick={() => { playClick(); setActiveTab('smart-paste') }}>
          <span className="tab-icon">📋</span> Smart SMS / UPI Parser
        </button>
        <button className={activeTab === 'statement' ? 'active' : ''} onClick={() => { playClick(); setActiveTab('statement') }}>
          <span className="tab-icon">📊</span> Statement CSV Importer
        </button>
        <button className={activeTab === 'guide' ? 'active' : ''} onClick={() => { playClick(); setActiveTab('guide') }}>
          <span className="tab-icon">📱</span> Android Auto-Sync Setup
        </button>
      </div>

      {/* Tab 1: Live Simulator */}
      {activeTab === 'simulate' && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="tab-content">
          <div className="simulator-grid">
            <div className="panel simulator-intro">
              <span className="section-kicker">INSTANT DEMO</span>
              <h2>Test Real-Time Ingestion</h2>
              <p>
                Click any realistic preset below. It fires raw bank SMS text directly to the live backend parser and webhook endpoint, updates the SQLite database, triggers celebration audio, and recalculates all metrics instantly.
              </p>
              <div className="api-badge">Endpoint: <code>POST /api/sync/sms</code></div>
            </div>

            <div className="preset-cards-grid">
              {SAMPLE_PRESETS.map((preset) => (
                <motion.div
                  key={preset.id}
                  className={`panel preset-card ${simulating === preset.id ? 'simulating' : ''}`}
                  whileHover={{ y: -3, scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <div className="preset-top">
                    <span className="preset-emoji">{preset.icon}</span>
                    <div>
                      <strong>{preset.label}</strong>
                      <small>{preset.desc}</small>
                    </div>
                    <span className={`preset-amount ${preset.id === 'salary' ? 'income' : ''}`}>{preset.amount}</span>
                  </div>
                  <p className="preset-sms-snippet">{preset.sms}</p>
                  <button
                    className="primary-button compact sim-btn"
                    disabled={simulating === preset.id}
                    onClick={() => triggerSimulation(preset)}
                  >
                    {simulating === preset.id ? 'Ingesting...' : 'Simulate Live Sync ↗'}
                  </button>
                </motion.div>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {/* Tab 2: Smart SMS / UPI Text Parser */}
      {activeTab === 'smart-paste' && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="tab-content">
          <div className="panel parse-panel">
            <span className="section-kicker">NLP REGEX PARSER</span>
            <h2>Paste Bank SMS or UPI Notification</h2>
            <p>
              Paste any transaction message from HDFC, SBI, ICICI, Axis, Kotak, PhonePe, Google Pay, or Paytm. The engine extracts amount, merchant, category, and date automatically.
            </p>

            <div className="sms-input-wrap">
              <textarea
                rows={3}
                value={smsInput}
                onChange={(e) => setSmsInput(e.target.value)}
                placeholder="e.g. Dear SBI User, A/C ...5678 debited by 450.0 on 13Sep26 trf to Swiggy UPI: 491823719283. Avl Bal: Rs 14,100"
              />
              <button className="primary-button" disabled={parsing || !smsInput.trim()} onClick={handleParseInput}>
                {parsing ? 'Parsing...' : 'Analyze & Preview ↗'}
              </button>
            </div>

            {parseError && <div className="error-banner">{parseError}</div>}

            {/* Parsed Preview Card */}
            {parsedPreview && (
              <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="parsed-preview-box">
                <div className="preview-header">
                  <span className="preview-tag">{parsedPreview.kind?.toUpperCase()}</span>
                  <h3>{parsedPreview.title}</h3>
                  <strong className={parsedPreview.kind === 'income' ? 'positive' : ''}>{money(parsedPreview.amount)}</strong>
                </div>
                <div className="preview-grid">
                  <div><span>Category:</span> <b>{parsedPreview.category}</b></div>
                  <div><span>Payment Method:</span> <b>{parsedPreview.payment_method}</b></div>
                  <div><span>Institution:</span> <b>{parsedPreview.institution || 'Bank'}</b></div>
                  <div><span>Account Ref:</span> <b>{parsedPreview.account_ref || 'Local'}</b></div>
                </div>
                <div className="preview-actions">
                  <button className="ghost-button" onClick={() => setParsedPreview(null)}>Discard</button>
                  <button className="primary-button" onClick={handleConfirmParsed}>Confirm & Save to Ledger ↗</button>
                </div>
              </motion.div>
            )}
          </div>
        </motion.div>
      )}

      {/* Tab 3: Statement CSV Importer */}
      {activeTab === 'statement' && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="tab-content">
          <div className="panel csv-panel">
            <span className="section-kicker">BATCH INGESTION</span>
            <h2>Import Bank or UPI Statements</h2>
            <p>Upload CSV or text exports downloaded from net banking or UPI apps (GPay, PhonePe, Paytm). We automatically check for duplicates.</p>

            <div className="dropzone" onClick={() => fileInputRef.current?.click()}>
              <input ref={fileInputRef} type="file" accept=".csv,.txt" hidden onChange={handleCsvUpload} />
              <span className="drop-icon">📁</span>
              <strong>{csvFile ? csvFile.name : 'Click to select CSV Statement file'}</strong>
              <small>Supports standard bank statement exports</small>
            </div>

            {importSummary && (
              <div className="import-success-banner">
                ✓ Successfully imported {importSummary.created_count} transactions ({importSummary.skipped_count} duplicates skipped).
              </div>
            )}

            {csvPreview.length > 0 && (
              <div className="csv-preview-list">
                <div className="csv-preview-header">
                  <strong>Preview: {csvPreview.length} Transactions Detected</strong>
                  <button className="primary-button compact" disabled={importing} onClick={commitCsvImport}>
                    {importing ? 'Importing...' : `Import All ${csvPreview.length} Now ↗`}
                  </button>
                </div>
                <div className="csv-table-scroll">
                  <table className="csv-table">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>Title / Description</th>
                        <th>Kind</th>
                        <th>Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {csvPreview.slice(0, 10).map((row, idx) => (
                        <tr key={idx}>
                          <td>{shortDate(row.date)}</td>
                          <td>{row.title}</td>
                          <td><span className={`badge-kind ${row.kind}`}>{row.kind}</span></td>
                          <td><strong>{money(row.amount)}</strong></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </motion.div>
      )}

      {/* Tab 4: Android Auto-Sync Setup Guide */}
      {activeTab === 'guide' && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="tab-content">
          <div className="panel guide-panel">
            <span className="section-kicker">ZERO-TOUCH AUTOMATION</span>
            <h2>How to Auto-Reflect Every UPI Spend from Your Phone</h2>
            <p className="guide-subtitle">
              Set up once in 2 minutes. Whenever you pay with Google Pay, PhonePe, Paytm, or Credit Card on your Android phone, it automatically reflects in Ledgerly in under 1 second!
            </p>

            <div className="guide-steps">
              <div className="step-card">
                <span className="step-num">1</span>
                <h3>Install MacroDroid or Tasker</h3>
                <p>Download <strong>MacroDroid</strong> (free on Google Play Store). It requires no coding and handles SMS automation seamlessly.</p>
              </div>

              <div className="step-card">
                <span className="step-num">2</span>
                <h3>Create New Macro</h3>
                <p>
                  <strong>Trigger:</strong> Select <code>SMS Received</code>.<br />
                  <strong>Filter:</strong> Set Sender matches: <code>*HDFC*, *SBI*, *ICICI*, *AXIS*, *KOTAK*, *PAYTM*</code>.
                </p>
              </div>

              <div className="step-card">
                <span className="step-num">3</span>
                <h3>Set HTTP POST Action</h3>
                <p>
                  <strong>Action:</strong> Select <code>HTTP Request</code>.<br />
                  <strong>Method:</strong> <code>POST</code><br />
                  <strong>URL:</strong> <code>http://&lt;YOUR_PC_IP&gt;:8000/sync/sms</code><br />
                  <strong>Content Type:</strong> <code>application/json</code><br />
                  <strong>Body:</strong> <code>&#123;"text": "[sms_body]"&#125;</code>
                </p>
              </div>

              <div className="step-card">
                <span className="step-num">4</span>
                <h3>That's It! Live Sync Active</h3>
                <p>
                  Make any UPI payment. The bank SMS triggers MacroDroid, sends the text payload to Ledgerly, and it appears instantly on your screen!
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* Advanced Metrics Grid */}
      {advancedAnalytics && (
        <section className="autosync-analytics-grid">
          {/* Payment Methods Breakdown */}
          <div className="panel method-breakdown-card">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">PAYMENT CHANNELS</span>
                <h2>UPI vs Cards vs Net Banking</h2>
              </div>
            </div>
            <div className="methods-list">
              {advancedAnalytics.payment_methods?.map((item) => (
                <div key={item.method} className="method-row">
                  <div className="method-meta">
                    <span className="method-name">{item.method}</span>
                    <span className="method-pct">{item.percentage}%</span>
                  </div>
                  <div className="method-bar-track">
                    <motion.div
                      className="method-bar-fill"
                      initial={{ width: 0 }}
                      animate={{ width: `${item.percentage}%` }}
                      transition={{ duration: 0.8 }}
                    />
                  </div>
                  <div className="method-amt">{money(item.amount)}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Top Merchants Leaderboard */}
          <div className="panel top-merchants-card">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">TOP BENEFICIARIES</span>
                <h2>Most Frequented Merchants</h2>
              </div>
            </div>
            <div className="merchants-list">
              {advancedAnalytics.top_merchants?.slice(0, 5).map((m, idx) => (
                <div key={m.name} className="merchant-row">
                  <span className="merchant-rank">#{idx + 1}</span>
                  <div className="merchant-info">
                    <strong>{m.name}</strong>
                    <small>{m.count} transactions · {m.category || 'Spend'}</small>
                  </div>
                  <b className="merchant-amount">{money(m.amount)}</b>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
export default AutoSyncHub
