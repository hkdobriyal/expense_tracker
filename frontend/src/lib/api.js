import axios from 'axios'
import { API } from './constants'

export async function fetchWorkspace() {
  const [transactions, accounts, budgets, goals, bills, summary] = await Promise.all([
    axios.get(`${API}/transactions`),
    axios.get(`${API}/accounts`),
    axios.get(`${API}/budgets`),
    axios.get(`${API}/goals`),
    axios.get(`${API}/bills`),
    axios.get(`${API}/dashboard/summary`).catch(() => ({ data: null })),
  ])
  return {
    transactions: transactions.data,
    accounts: accounts.data,
    budgets: budgets.data,
    goals: goals.data,
    bills: bills.data,
    summary: summary.data,
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
