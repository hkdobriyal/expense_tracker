import axios from 'axios'
import { API } from './constants'

export async function fetchWorkspace() {
  const [transactions, accounts, budgets, goals, bills, summary, analytics] = await Promise.all([
    axios.get(`${API}/transactions`),
    axios.get(`${API}/accounts`),
    axios.get(`${API}/budgets`),
    axios.get(`${API}/goals`),
    axios.get(`${API}/bills`),
    axios.get(`${API}/dashboard/summary`).catch(() => ({ data: null })),
    axios.get(`${API}/analytics/advanced`).catch(() => ({ data: null })),
  ])
  return {
    transactions: transactions.data,
    accounts: accounts.data,
    budgets: budgets.data,
    goals: goals.data,
    bills: bills.data,
    summary: summary.data,
    analytics: analytics.data,
  }
}

export function saveTransaction(payload, id) {
  return id ? axios.put(`${API}/transactions/${id}`, payload) : axios.post(`${API}/transactions`, payload)
}

export function deleteTransaction(id) {
  return axios.delete(`${API}/transactions/${id}`)
}

export function saveResource(route, payload, id) {
  return id ? axios.put(`${API}/${route}/${id}`, payload) : axios.post(`${API}/${route}`, payload)
}

export function deleteResource(route, id) {
  return axios.delete(`${API}/${route}/${id}`)
}

export function restoreBackup(payload) {
  return axios.post(`${API}/backup/restore`, payload)
}

export function parseSMSText(text) {
  return axios.post(`${API}/sync/parse-text`, { text })
}

export function syncSMSWebhook(text) {
  return axios.post(`${API}/sync/sms`, { text })
}

export function importBatchTransactions(transactions) {
  return axios.post(`${API}/transactions/batch`, { transactions })
}

export function fetchAdvancedAnalytics() {
  return axios.get(`${API}/analytics/advanced`)
}

// --- RBI Account Aggregator (AA) & Direct Statement APIs ---

export function fetchFIPs() {
  return axios.get(`${API}/aa/fips`)
}

export function createAAConsent(payload) {
  return axios.post(`${API}/aa/consent`, payload)
}

export function verifyAAOtp(payload) {
  return axios.post(`${API}/aa/consent/verify-otp`, payload)
}

export function checkAAStatus(handle) {
  return axios.get(`${API}/aa/consent/${handle}/status`)
}

export function fetchAAData(payload) {
  return axios.post(`${API}/aa/fetch`, payload)
}

export function uploadBankStatement(formData) {
  return axios.post(`${API}/statements/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getAAConfig() {
  return axios.get(`${API}/aa/config`)
}

export function saveAAConfig(payload) {
  return axios.post(`${API}/aa/config`, payload)
}

