import React, { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { fetchFIPs, createAAConsent, verifyAAOtp, fetchAAData, uploadBankStatement, getAAConfig, saveAAConfig } from '../lib/api'
import { money, shortDate } from '../lib/format'
import { playChime, playClick, playCoin } from '../lib/sound'
import { fireCelebrationConfetti, fireGoldBurst } from '../lib/confetti'

export function AccountAggregatorHub({ onTransactionAdded, advancedAnalytics }) {
  const [activeTab, setActiveTab] = useState('aa') // 'aa' or 'statement'
  const [fips, setFips] = useState([])
  const [selectedFip, setSelectedFip] = useState(null)
  const [mobileNumber, setMobileNumber] = useState('9876543210')
  const [aaStep, setAaStep] = useState(1) // 1: Bank Select, 2: OTP, 3: Discovered Accounts, 4: Success
  const [consentHandle, setConsentHandle] = useState('')
  const [otp, setOtp] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [discoveredAccounts, setDiscoveredAccounts] = useState([])
  const [activeConsentId, setActiveConsentId] = useState('')
  const [syncSummary, setSyncSummary] = useState(null)
  const [aaConfig, setAaConfig] = useState({ provider: 'sandbox', has_credentials: false })
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [configForm, setConfigForm] = useState({
    provider: 'sandbox',
    client_id: '',
    client_secret: '',
    product_instance_id: '',
    environment: 'sandbox',
  })

  // Statement PDF/CSV state
  const [statementFile, setStatementFile] = useState(null)
  const [pdfPassword, setPdfPassword] = useState('')
  const [uploadingStatement, setUploadingStatement] = useState(false)
  const [statementResult, setStatementResult] = useState(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    fetchFIPs()
      .then((res) => {
        setFips(res.data)
        if (res.data.length > 0) setSelectedFip(res.data[0])
      })
      .catch(() => {
        const fallbacks = [
          { id: 'FIP-HDFC', name: 'HDFC Bank', short_name: 'HDFC', brand_color: '#004c8f', logo_text: 'HDFC' },
          { id: 'FIP-SBI', name: 'State Bank of India', short_name: 'SBI', brand_color: '#280071', logo_text: 'SBI' },
          { id: 'FIP-ICICI', name: 'ICICI Bank', short_name: 'ICICI', brand_color: '#f37021', logo_text: 'ICICI' },
          { id: 'FIP-AXIS', name: 'Axis Bank', short_name: 'Axis', brand_color: '#97144d', logo_text: 'AXIS' },
          { id: 'FIP-KOTAK', name: 'Kotak Mahindra Bank', short_name: 'Kotak', brand_color: '#ed1c24', logo_text: 'KOTAK' },
          { id: 'FIP-PNB', name: 'Punjab National Bank', short_name: 'PNB', brand_color: '#a20e26', logo_text: 'PNB' },
        ]
        setFips(fallbacks)
        setSelectedFip(fallbacks[0])
      })

    getAAConfig()
      .then((res) => {
        setAaConfig(res.data)
        setConfigForm((prev) => ({ ...prev, ...res.data }))
      })
      .catch(() => {})
  }, [])

  // Step 1: Initiate ReBIT Consent Request
  async function handleInitiateConsent() {
    if (!selectedFip || !mobileNumber || mobileNumber.length < 10) {
      setErrorMessage('Please enter a valid 10-digit mobile number linked to your bank account.')
      return
    }
    try {
      playClick()
      setLoading(true)
      setErrorMessage('')
      const res = await createAAConsent({
        fip_id: selectedFip.id,
        mobile_number: mobileNumber,
      })
      if (res.data.success) {
        setConsentHandle(res.data.consent_handle)
        setAaStep(2)
        setOtp('123456') // Pre-fill test OTP for sandbox
        playCoin()
      }
    } catch {
      setErrorMessage('Could not initiate RBI Account Aggregator consent request.')
    } finally {
      setLoading(false)
    }
  }

  // Step 2: Verify OTP and discover accounts
  async function handleVerifyOtp() {
    if (!otp || otp.length !== 6) {
      setErrorMessage('Please enter the 6-digit OTP.')
      return
    }
    try {
      playClick()
      setLoading(true)
      setErrorMessage('')
      const res = await verifyAAOtp({
        consent_handle: consentHandle,
        otp: otp,
      })
      if (res.data.success) {
        setDiscoveredAccounts(res.data.discovered_accounts)
        setActiveConsentId(res.data.consent_id)
        setAaStep(3)
        playChime()
        fireGoldBurst()
      }
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Invalid or expired OTP.')
    } finally {
      setLoading(false)
    }
  }

  // Step 3: Stream direct bank transactions into SQLite
  async function handleFetchFinancialData() {
    if (!activeConsentId || !selectedFip) return
    try {
      playClick()
      setLoading(true)
      setErrorMessage('')
      const res = await fetchAAData({
        consent_id: activeConsentId,
        fip_id: selectedFip.id,
      })
      if (res.data.success) {
        setSyncSummary(res.data)
        setAaStep(4)
        playChime()
        fireCelebrationConfetti()
        if (onTransactionAdded) onTransactionAdded()
      }
    } catch {
      setErrorMessage('Failed to stream direct bank statement data.')
    } finally {
      setLoading(false)
    }
  }

  function handleResetFlow() {
    playClick()
    setAaStep(1)
    setOtp('')
    setSyncSummary(null)
    setDiscoveredAccounts([])
    setErrorMessage('')
  }

  async function handleSaveConfig(e) {
    e.preventDefault()
    try {
      playClick()
      const res = await saveAAConfig(configForm)
      setAaConfig(res.data)
      setShowConfigModal(false)
      playChime()
    } catch {
      setErrorMessage('Failed to update Account Aggregator credentials')
    }
  }

  // Statement PDF/CSV upload
  function handleFileSelect(e) {
    const file = e.target.files?.[0]
    if (file) {
      setStatementFile(file)
      setStatementResult(null)
      setErrorMessage('')
      playClick()
    }
  }

  async function handleUploadStatement() {
    if (!statementFile) return
    const formData = new FormData()
    formData.append('file', statementFile)
    if (pdfPassword.trim()) {
      formData.append('password', pdfPassword.trim())
    }

    try {
      playClick()
      setUploadingStatement(true)
      setErrorMessage('')
      const res = await uploadBankStatement(formData)
      if (res.data.success) {
        setStatementResult(res.data)
        playChime()
        fireCelebrationConfetti()
        if (onTransactionAdded) onTransactionAdded()
      } else {
        setErrorMessage(res.data.message || 'Could not parse bank statement')
      }
    } catch (err) {
      setErrorMessage(err.response?.data?.detail || 'Failed to parse statement. If this is a password-protected PDF, enter your PAN or DOB.')
    } finally {
      setUploadingStatement(false)
    }
  }

  return (
    <div className="autosync-hub-view aa-hub-view">
      {/* Header Banner */}
      <section className="autosync-hero panel">
        <div className="autosync-hero-text">
          <div className="rbi-shield-badge">
            <span className="shield-icon">🛡️</span>
            <span>RBI ACCOUNT AGGREGATOR FRAMEWORK · ReBIT 1.1.2 SPEC</span>
          </div>
          <h1>Direct Bank Statement Ingestion</h1>
          <p>
            No SMS. No email scraping. Directly connect your bank via the <strong>Reserve Bank of India (RBI) Account Aggregator framework</strong> or upload official password-protected PDF / CSV NetBanking statements.
          </p>

          <div className="aa-mode-switch-row">
            <div className={`mode-badge ${aaConfig.provider === 'setu' ? 'live' : 'sandbox'}`}>
              <span className="mode-dot" />
              <span>{aaConfig.provider === 'setu' ? 'Live Setu AA Connected' : 'ReBIT Local Sandbox Mode'}</span>
            </div>
            <button className="text-button aa-config-trigger" onClick={() => { playClick(); setShowConfigModal(true) }}>
              ⚙ Configure Live API Keys ↗
            </button>
          </div>
        </div>

        {advancedAnalytics && (
          <div className="autosync-health-card">
            <div className="health-score-ring">
              <span className="score-num">{advancedAnalytics.financial_health_score || 78}</span>
              <span className="score-sub">FINANCIAL HEALTH</span>
            </div>
            <div className="health-stats">
              <div>
                <span>SECURITY LEVEL</span>
                <strong style={{ color: '#7ef0c2' }}>E2E Encrypted</strong>
              </div>
              <div>
                <span>30-DAY OUTFLOW</span>
                <strong>{money(advancedAnalytics.last_30_days_expense || 0)}</strong>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Main Tabs */}
      <div className="autosync-tabs">
        <button className={activeTab === 'aa' ? 'active' : ''} onClick={() => { playClick(); setActiveTab('aa') }}>
          <span className="tab-icon">🏦</span> RBI Account Aggregator (Live Stream)
        </button>
        <button className={activeTab === 'statement' ? 'active' : ''} onClick={() => { playClick(); setActiveTab('statement') }}>
          <span className="tab-icon">📄</span> Official Statement Importer (PDF / CSV)
        </button>
      </div>

      {errorMessage && <div className="error-banner">{errorMessage}</div>}

      {/* TAB 1: RBI Account Aggregator Connect Flow */}
      {activeTab === 'aa' && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="tab-content">
          <div className="panel aa-connect-panel">
            {/* Step Progress Bar */}
            <div className="aa-steps-indicator">
              <div className={`step-node ${aaStep >= 1 ? 'active' : ''}`}>
                <span className="node-num">1</span>
                <span>Select Bank</span>
              </div>
              <div className="step-connector" />
              <div className={`step-node ${aaStep >= 2 ? 'active' : ''}`}>
                <span className="node-num">2</span>
                <span>OTP Consent</span>
              </div>
              <div className="step-connector" />
              <div className={`step-node ${aaStep >= 3 ? 'active' : ''}`}>
                <span className="node-num">3</span>
                <span>Linked Accounts</span>
              </div>
              <div className="step-connector" />
              <div className={`step-node ${aaStep >= 4 ? 'active' : ''}`}>
                <span className="node-num">4</span>
                <span>Direct Sync</span>
              </div>
            </div>

            {/* Step 1: Bank Selection & Mobile */}
            {aaStep === 1 && (
              <div className="aa-step-box">
                <span className="section-kicker">STEP 1 OF 3 · SELECT FINANCIAL INFORMATION PROVIDER (FIP)</span>
                <h2>Choose Your Primary Bank</h2>
                <p className="step-subtitle">
                  Select your bank to initiate direct transaction streaming under RBI NBFC-AA regulations.
                </p>

                <div className="fip-grid">
                  {fips.map((fip) => (
                    <motion.div
                      key={fip.id}
                      className={`fip-card ${selectedFip?.id === fip.id ? 'selected' : ''}`}
                      onClick={() => { playClick(); setSelectedFip(fip) }}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      style={{ '--bank-color': fip.brand_color }}
                    >
                      <div className="fip-avatar" style={{ background: fip.brand_color }}>
                        {fip.logo_text || fip.name.slice(0, 2)}
                      </div>
                      <div className="fip-info">
                        <strong>{fip.name}</strong>
                        <small>RBI Registered FIP</small>
                      </div>
                      <span className="fip-check">{selectedFip?.id === fip.id ? '✓' : ''}</span>
                    </motion.div>
                  ))}
                </div>

                <div className="aa-mobile-form">
                  <label>
                    Mobile Number Linked to {selectedFip?.name || 'Bank'}:
                    <div className="mobile-input-wrap">
                      <span className="country-code">+91</span>
                      <input
                        type="tel"
                        maxLength={10}
                        value={mobileNumber}
                        onChange={(e) => setMobileNumber(e.target.value.replace(/\D/g, ''))}
                        placeholder="9876543210"
                      />
                    </div>
                  </label>

                  <div className="consent-terms-notice">
                    <span className="lock-icon">🔒</span>
                    <div>
                      <strong>Encrypted Consent Artifact</strong>
                      <small>
                        Data Type: Transactions & Summary · Mode: Periodic · Encrypted using ECC Curve25519 per ReBIT guidelines. Data remains strictly on your local device.
                      </small>
                    </div>
                  </div>

                  <button className="primary-button" disabled={loading} onClick={handleInitiateConsent}>
                    {loading ? 'Initiating Consent...' : `Connect ${selectedFip?.name || 'Bank'} via RBI AA ↗`}
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: OTP Verification */}
            {aaStep === 2 && (
              <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="aa-step-box otp-box">
                <span className="section-kicker">STEP 2 OF 3 · RBI CONSENT AUTHORIZATION</span>
                <h2>Authorize Consent with 6-Digit OTP</h2>
                
                {/* Clear explanation why no physical SMS arrives in sandbox */}
                <div className="sandbox-info-card">
                  <div className="info-title">
                    <span>💡</span> <strong>Why am I not receiving a physical SMS OTP?</strong>
                  </div>
                  <p>
                    Indian banks (HDFC, SBI, ICICI) <strong>strictly require an official RBI FIU commercial license</strong> to dispatch live SMS OTPs from a local computer on <code>localhost</code>.
                  </p>
                  <p>
                    Ledgerly has simulated the full ReBIT AA consent handshake locally. <strong>Use test OTP <code>123456</code></strong> below to authorize.
                  </p>
                  <small>
                    <em>Note: To import your genuine bank data right now without waiting, switch to the <strong>Official Statement Importer</strong> tab to upload your actual NetBanking PDF!</em>
                  </small>
                </div>

                <div className="otp-input-row">
                  <input
                    type="text"
                    maxLength={6}
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                    placeholder="123456"
                    className="otp-field"
                    autoFocus
                  />
                  <div className="otp-helper-badge">Sandbox Pre-filled OTP: <code>123456</code></div>
                </div>

                <div className="otp-actions">
                  <button className="ghost-button" onClick={() => setAaStep(1)}>← Back</button>
                  <button className="primary-button" disabled={loading || otp.length !== 6} onClick={handleVerifyOtp}>
                    {loading ? 'Verifying OTP...' : 'Authorize Consent ↗'}
                  </button>
                </div>
              </motion.div>
            )}

            {/* Step 3: Discovered Accounts */}
            {aaStep === 3 && (
              <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="aa-step-box">
                <span className="section-kicker">STEP 3 OF 3 · ACCOUNTS DISCOVERED</span>
                <h2>Linked Bank Accounts at {selectedFip?.name}</h2>
                <p className="step-subtitle">
                  The Account Aggregator verified your identity and fetched your active account details.
                </p>

                <div className="discovered-accounts-list">
                  {discoveredAccounts.map((acc, idx) => (
                    <div className="discovered-card" key={idx}>
                      <div className="discovered-top">
                        <span className="bank-pill">{acc.institution}</span>
                        <span className="type-pill">{acc.account_type}</span>
                        <strong className="acc-bal">{money(acc.balance)}</strong>
                      </div>
                      <div className="discovered-body">
                        <div><span>Account No:</span> <b>{acc.account_number}</b></div>
                        <div><span>IFSC:</span> <b>{acc.ifsc}</b></div>
                        <div><span>Branch:</span> <b>{acc.branch}</b></div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="stream-action-box">
                  <button className="primary-button large" disabled={loading} onClick={handleFetchFinancialData}>
                    {loading ? 'Streaming Statements...' : '⚡ Stream Direct Bank Statement to Ledger ↗'}
                  </button>
                </div>
              </motion.div>
            )}

            {/* Step 4: Sync Success Summary */}
            {aaStep === 4 && syncSummary && (
              <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} className="aa-step-box success-box">
                <div className="success-icon">✓</div>
                <h2>Direct Bank Transactions Synced!</h2>
                <p className="step-subtitle">
                  Direct bank statement successfully decrypted and saved to your local ledger.
                </p>

                <div className="sync-stats-row">
                  <div className="sync-stat">
                    <span>TRANSACTIONS ADDED</span>
                    <strong>{syncSummary.created_count}</strong>
                  </div>
                  <div className="sync-stat">
                    <span>DUPLICATES PREVENTED</span>
                    <strong>{syncSummary.skipped_count}</strong>
                  </div>
                  <div className="sync-stat">
                    <span>BANK LINKED</span>
                    <strong>{selectedFip?.name}</strong>
                  </div>
                </div>

                <div className="otp-actions" style={{ marginTop: '20px' }}>
                  <button className="primary-button" onClick={handleResetFlow}>
                    Sync Another Bank or Refresh ↺
                  </button>
                </div>
              </motion.div>
            )}
          </div>
        </motion.div>
      )}

      {/* TAB 2: Direct PDF / CSV Statement Importer */}
      {activeTab === 'statement' && (
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="tab-content">
          <div className="panel statement-panel">
            <span className="section-kicker">GENUINE BANK STATEMENTS</span>
            <h2>Upload NetBanking Statement (PDF / CSV)</h2>
            <p>
              Want your <strong>100% genuine bank transactions</strong> right now without any developer keys? Download your monthly statement from HDFC NetBanking, SBI YONO, or ICICI iMobile and drop it here. We support password-protected bank PDFs.
            </p>

            <div className="statement-dropzone" onClick={() => fileInputRef.current?.click()}>
              <input ref={fileInputRef} type="file" accept=".pdf,.csv,.txt" hidden onChange={handleFileSelect} />
              <span className="drop-icon">📄</span>
              <strong>{statementFile ? statementFile.name : 'Click or drop PDF / CSV Bank Statement here'}</strong>
              <small>Supported formats: Official PDF statements, CSV exports from HDFC, SBI, ICICI, Axis</small>
            </div>

            {/* Password input if file is PDF */}
            {statementFile?.name?.toLowerCase().endsWith('.pdf') && (
              <div className="pdf-password-wrap">
                <label>
                  Statement PDF Password (if protected):
                  <input
                    type="password"
                    value={pdfPassword}
                    onChange={(e) => setPdfPassword(e.target.value)}
                    placeholder="e.g. PAN in capital letters + Date of Birth"
                  />
                </label>
                <small className="password-hint">
                  💡 Hint: Indian banks usually protect PDFs with: <strong>PAN uppercase + DOB (DDMMYYYY)</strong> or <strong>First 4 letters of Name + Last 4 digits of Mobile</strong>.
                </small>
              </div>
            )}

            {statementFile && (
              <div className="statement-action-row">
                <button
                  className="primary-button"
                  disabled={uploadingStatement}
                  onClick={handleUploadStatement}
                >
                  {uploadingStatement ? 'Decrypting & Parsing...' : `Import ${statementFile.name} ↗`}
                </button>
              </div>
            )}

            {/* Statement Results Banner & Table */}
            {statementResult && (
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="statement-results-wrap">
                <div className="import-success-banner">
                  ✓ Successfully imported {statementResult.created_count} transactions from {statementResult.bank_detected} ({statementResult.skipped_count} duplicates skipped).
                </div>

                {statementResult.transactions?.length > 0 && (
                  <div className="csv-preview-list">
                    <div className="csv-preview-header">
                      <strong>Sample Transactions Decoded from {statementResult.bank_detected} Statement</strong>
                    </div>
                    <div className="csv-table-scroll">
                      <table className="csv-table">
                        <thead>
                          <tr>
                            <th>Date</th>
                            <th>Decoded Title</th>
                            <th>Category</th>
                            <th>Payment Channel</th>
                            <th>Amount</th>
                          </tr>
                        </thead>
                        <tbody>
                          {statementResult.transactions.slice(0, 8).map((txn, idx) => (
                            <tr key={idx}>
                              <td>{shortDate(txn.date)}</td>
                              <td><strong>{txn.title}</strong></td>
                              <td><span className="category-pill">{txn.category}</span></td>
                              <td>{txn.payment_method}</td>
                              <td><b className={txn.kind === 'income' ? 'positive' : ''}>{money(txn.amount)}</b></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </motion.div>
            )}
          </div>
        </motion.div>
      )}

      {/* Setu Live AA Config Modal */}
      {showConfigModal && (
        <div className="modal-backdrop" onClick={() => setShowConfigModal(false)}>
          <div className="capture-modal config-modal" onClick={(e) => e.stopPropagation()}>
            <div className="shortcuts-modal-header">
              <div>
                <span className="section-kicker">RBI ACCOUNT AGGREGATOR</span>
                <h2>⚙ Live API Configuration</h2>
              </div>
              <button className="icon-button" onClick={() => setShowConfigModal(false)}>✕</button>
            </div>

            <form onSubmit={handleSaveConfig} className="config-form">
              <p className="config-info-text">
                To send <strong>real live SMS OTPs</strong> to a user's phone, you must provide your RBI-licensed NBFC-AA API credentials (e.g. from <a href="https://setu.co" target="_blank" rel="noreferrer">Setu.co</a>).
              </p>

              <label>
                Integration Provider:
                <select
                  value={configForm.provider}
                  onChange={(e) => setConfigForm({ ...configForm, provider: e.target.value })}
                >
                  <option value="sandbox">Local ReBIT Sandbox (Zero Setup · Simulated OTP)</option>
                  <option value="setu">Setu Account Aggregator (Live SMS & Consent Bridge)</option>
                </select>
              </label>

              {configForm.provider === 'setu' && (
                <>
                  <label>
                    Setu Client ID:
                    <input
                      required
                      value={configForm.client_id}
                      onChange={(e) => setConfigForm({ ...configForm, client_id: e.target.value })}
                      placeholder="e.g. 8f81...712b"
                    />
                  </label>
                  <label>
                    Setu Client Secret:
                    <input
                      required
                      type="password"
                      value={configForm.client_secret}
                      onChange={(e) => setConfigForm({ ...configForm, client_secret: e.target.value })}
                      placeholder="••••••••••••••••"
                    />
                  </label>
                  <label>
                    Product Instance ID:
                    <input
                      required
                      value={configForm.product_instance_id}
                      onChange={(e) => setConfigForm({ ...configForm, product_instance_id: e.target.value })}
                      placeholder="e.g. fiu-instance-1"
                    />
                  </label>
                </>
              )}

              <div className="config-actions">
                <button type="button" className="ghost-button" onClick={() => setShowConfigModal(false)}>Cancel</button>
                <button type="submit" className="primary-button">Save Configuration ↗</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default AccountAggregatorHub
