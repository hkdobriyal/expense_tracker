import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useContext } from 'react'
import { api } from './api'

// Shared reference data used by forms across the app.
export const useAccounts = () => useQuery({ queryKey: ['accounts'], queryFn: () => api.get('/accounts') })
export const useCategories = () => useQuery({ queryKey: ['categories'], queryFn: () => api.get('/categories'), staleTime: 60_000 })
export const useTags = () => useQuery({ queryKey: ['tags'], queryFn: () => api.get('/tags'), staleTime: 60_000 })

// A ledger change can affect every derived number (balances, budgets, analytics, alerts),
// so after any write we invalidate everything. One source of truth, no stale screens.
export function useLedgerMutation(fn, { onSuccess, onError } = {}) {
  const qc = useQueryClient()
  const toast = useToast()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data, vars) => {
      qc.invalidateQueries()
      onSuccess?.(data, vars)
    },
    onError: (error, vars) => {
      if (onError) onError(error, vars)
      else toast.error(error.message)
    },
  })
}

export const ToastContext = createContext({ show: () => {}, error: () => {}, success: () => {} })
export const useToast = () => useContext(ToastContext)

export const SessionContext = createContext(null)
export const useSession = () => useContext(SessionContext)

export function categoryTree(categories = [], kind) {
  const list = kind ? categories.filter((c) => c.kind === kind && !c.is_archived) : categories
  const parents = list.filter((c) => !c.parent_id).sort((a, b) => a.name.localeCompare(b.name))
  return parents.map((p) => ({ ...p, children: list.filter((c) => c.parent_id === p.id).sort((a, b) => a.name.localeCompare(b.name)) }))
}
