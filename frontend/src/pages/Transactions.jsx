import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ArrowLeftRight, CheckCheck, Copy, Filter, Pencil, Plus, Search, Tag, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useActions } from '../components/Layout'
import { categoryOptions } from '../components/TransactionForm'
import { Badge, Button, Card, Confirm, Empty, ErrorNote, Loading, Money, PageHead, Select } from '../components/ui'
import { api } from '../lib/api'
import { TYPE_LABEL, longDate, money, shortDate, signedAmount } from '../lib/format'
import { useAccounts, useCategories, useLedgerMutation, useToast } from '../lib/hooks'

const FILTER_KEYS = ['q', 'type', 'account_id', 'category_id', 'merchant_id', 'tag', 'reviewed', 'source', 'start', 'end', 'min_amount', 'max_amount', 'uncategorized']
const SOURCES = ['manual', 'import', 'bank', 'sms', 'recurring', 'bill', 'restore', 'demo']

export default function Transactions() {
  const [params, setParams] = useSearchParams()
  const { addTransaction, editTransaction } = useActions()
  const toast = useToast()
  const { data: accounts = [] } = useAccounts()
  const { data: categories = [] } = useCategories()
  const [search, setSearch] = useState(params.get('q') || '')
  const [selected, setSelected] = useState(new Set())
  const [confirm, setConfirm] = useState(null)
  const [showFilters, setShowFilters] = useState(FILTER_KEYS.some((k) => k !== 'q' && params.get(k)))
  const page = Number(params.get('page') || 1)
  const sort = params.get('sort') || 'date'
  const order = params.get('order') || 'desc'

  useEffect(() => {
    const t = setTimeout(() => update({ q: search || null }), 300)
    return () => clearTimeout(t)
  }, [search]) // eslint-disable-line react-hooks/exhaustive-deps

  function update(patch, resetPage = true) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) (v === null || v === '' || v === undefined ? next.delete(k) : next.set(k, v))
    if (resetPage && !('page' in patch)) next.delete('page')
    setParams(next, { replace: true })
  }

  const query = useMemo(() => {
    const q = { page, page_size: 50, sort, order }
    FILTER_KEYS.forEach((k) => { if (params.get(k)) q[k] = params.get(k) })
    return q
  }, [params, page, sort, order])
  const list = useQuery({ queryKey: ['transactions', query], queryFn: () => api.get('/transactions', query), placeholderData: keepPreviousData })
  useEffect(() => setSelected(new Set()), [query])

  const bulk = useLedgerMutation((body) => api.post('/transactions/bulk', body), { onSuccess: (r) => { toast.success(`${r.updated} transaction(s) updated`); setSelected(new Set()); setConfirm(null) } })
  const remove = useLedgerMutation((id) => api.delete(`/transactions/${id}`), { onSuccess: () => { toast.success('Transaction deleted'); setConfirm(null) } })
  const duplicate = useLedgerMutation((id) => api.post(`/transactions/${id}/duplicate`), { onSuccess: () => toast.success('Duplicated – edit the copy to change its date') })
  const quickCategory = useLedgerMutation(({ id, category_id }) => api.patch(`/transactions/${id}`, { category_id }), { onSuccess: () => toast.success('Categorised') })

  const items = list.data?.items || []
  const allSelected = items.length > 0 && items.every((t) => selected.has(t.id))
  const toggle = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const catOpts = useMemo(() => [...categoryOptions(categories, 'expense'), ...categoryOptions(categories, 'income')], [categories])
  const sortBy = (key) => update({ sort: key, order: sort === key && order === 'desc' ? 'asc' : 'desc' })
  const s = list.data?.summary

  return (
    <>
      <PageHead kicker="Ledger" title="Transactions" actions={<Button variant="primary" icon={Plus} onClick={() => addTransaction()}>Add transaction</Button>}>
        Every income, expense, transfer and refund across your accounts.
      </PageHead>
      <Card>
        <div className="toolbar">
          <div className="search"><Search size={16} /><input className="input" placeholder="Search description, merchant, notes…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search transactions" /></div>
          <Select value={params.get('type') || ''} onChange={(e) => update({ type: e.target.value })} placeholder="All types" options={Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label }))} aria-label="Type" />
          <Select value={params.get('account_id') || ''} onChange={(e) => update({ account_id: e.target.value })} placeholder="All accounts" options={accounts.map((a) => ({ value: String(a.id), label: a.name }))} aria-label="Account" />
          <Button icon={Filter} onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>Filters</Button>
          <Button variant={params.get('reviewed') === 'false' ? 'primary' : undefined} icon={CheckCheck} onClick={() => update({ reviewed: params.get('reviewed') === 'false' ? null : 'false' })}>To review</Button>
        </div>
        {showFilters && (
          <div className="toolbar">
            <Select value={params.get('category_id') || ''} onChange={(e) => update({ category_id: e.target.value, uncategorized: null })} placeholder="All categories" options={catOpts} aria-label="Category" />
            <label className="checkbox"><input type="checkbox" checked={params.get('uncategorized') === 'true'} onChange={(e) => update({ uncategorized: e.target.checked ? 'true' : null, category_id: null })} />Uncategorised</label>
            <input className="input" type="date" aria-label="From date" value={params.get('start') || ''} onChange={(e) => update({ start: e.target.value })} />
            <input className="input" type="date" aria-label="To date" value={params.get('end') || ''} onChange={(e) => update({ end: e.target.value })} />
            <input className="input" style={{ width: 110, minWidth: 0 }} inputMode="decimal" placeholder="Min ₹" aria-label="Minimum amount" value={params.get('min_amount') || ''} onChange={(e) => update({ min_amount: e.target.value })} />
            <input className="input" style={{ width: 110, minWidth: 0 }} inputMode="decimal" placeholder="Max ₹" aria-label="Maximum amount" value={params.get('max_amount') || ''} onChange={(e) => update({ max_amount: e.target.value })} />
            <input className="input" style={{ width: 130, minWidth: 0 }} placeholder="Tag" aria-label="Tag" value={params.get('tag') || ''} onChange={(e) => update({ tag: e.target.value })} />
            <Select value={params.get('source') || ''} onChange={(e) => update({ source: e.target.value })} placeholder="Any source" options={SOURCES.map((x) => ({ value: x, label: x }))} aria-label="Import source" />
            <Button variant="ghost" onClick={() => { setSearch(''); setParams({}, { replace: true }) }}>Clear all</Button>
          </div>
        )}
        {s && (
          <div className="row wrap faint" style={{ fontSize: 13, marginBottom: 10, gap: 16 }}>
            <span>{list.data.total} transactions</span>
            <span>Income <Money minor={s.income} currency={s.currency} className="income" /></span>
            <span>Expenses <Money minor={s.expenses} currency={s.currency} className="expense" /></span>
            {s.invested > 0 && <span>Invested <Money minor={s.invested} currency={s.currency} /></span>}
          </div>
        )}
        {selected.size > 0 && (
          <div className="bulkbar" role="region" aria-label="Bulk actions">
            <strong>{selected.size} selected</strong>
            <Select value="" onChange={(e) => e.target.value && bulk.mutate({ ids: [...selected], action: 'categorize', category_id: Number(e.target.value) })} placeholder="Set category…" options={catOpts} aria-label="Set category" />
            <Button size="sm" icon={CheckCheck} onClick={() => bulk.mutate({ ids: [...selected], action: 'mark_reviewed' })}>Mark reviewed</Button>
            <Button size="sm" icon={Tag} onClick={() => { const tag = window.prompt('Tag to add'); if (tag) bulk.mutate({ ids: [...selected], action: 'add_tag', tag }) }}>Add tag</Button>
            <Button size="sm" variant="danger" icon={Trash2} onClick={() => setConfirm({ bulk: true })}>Delete</Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
          </div>
        )}
        <ErrorNote error={list.error} onRetry={list.refetch} />
        {list.isLoading ? <Loading rows={8} /> : items.length === 0 ? (
          <Empty icon={ArrowLeftRight} title={list.data?.total === 0 && !params.toString() ? 'No transactions yet' : 'Nothing matches these filters'} action={<Button variant="primary" icon={Plus} onClick={() => addTransaction()}>Add transaction</Button>} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 34 }}><input type="checkbox" aria-label="Select all on page" checked={allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(items.map((t) => t.id)))} /></th>
                  <th><button type="button" className="btn ghost sm" onClick={() => sortBy('date')}>Date {sort === 'date' ? (order === 'desc' ? '↓' : '↑') : ''}</button></th>
                  <th><button type="button" className="btn ghost sm" onClick={() => sortBy('description')}>Description {sort === 'description' ? (order === 'desc' ? '↓' : '↑') : ''}</button></th>
                  <th className="hide-mobile">Category</th>
                  <th className="hide-mobile">Account</th>
                  <th className="amount"><button type="button" className="btn ghost sm" onClick={() => sortBy('amount')}>Amount {sort === 'amount' ? (order === 'desc' ? '↓' : '↑') : ''}</button></th>
                  <th style={{ width: 110 }}><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => {
                  const signed = signedAmount(t)
                  return (
                    <tr key={t.id}>
                      <td><input type="checkbox" aria-label={`Select ${t.description}`} checked={selected.has(t.id)} onChange={() => toggle(t.id)} /></td>
                      <td className="faint" style={{ whiteSpace: 'nowrap' }} title={longDate(t.date)}>{shortDate(t.date)}</td>
                      <td style={{ maxWidth: 320 }}>
                        <div className="truncate" style={{ fontWeight: 600 }}>{t.description}</div>
                        <div className="row wrap" style={{ gap: 5, marginTop: 3 }}>
                          {t.type !== 'expense' && <Badge tone={t.type === 'income' || t.type === 'refund' ? 'success' : 'violet'}>{TYPE_LABEL[t.type]}</Badge>}
                          {t.merchant && t.merchant !== t.description && <span className="faint" style={{ fontSize: 12 }}>{t.merchant}</span>}
                          {!t.reviewed && <Badge tone="warning">review</Badge>}
                          {t.splits.length > 0 && <Badge>split ×{t.splits.length}</Badge>}
                          {t.tags.map((x) => <Badge key={x.id} tone="accent">#{x.name}</Badge>)}
                          {t.source !== 'manual' && <span className="faint" style={{ fontSize: 11 }}>{t.source}</span>}
                        </div>
                      </td>
                      <td className="hide-mobile">
                        {t.type === 'transfer' ? <span className="faint">→ {t.transfer_account_name}</span>
                          : t.splits.length ? <span className="faint">{t.splits.map((x) => x.category).join(', ')}</span>
                            : !t.reviewed || !t.category_id ? (
                              <Select value={t.category_id ? String(t.category_id) : ''} onChange={(e) => e.target.value && quickCategory.mutate({ id: t.id, category_id: Number(e.target.value) })} placeholder="Uncategorised" options={categoryOptions(categories, t.type === 'income' ? 'income' : 'expense')} aria-label="Category" />
                            ) : (
                              <span className="row" style={{ gap: 7 }}><span className="dot" style={{ background: t.category_color || 'var(--text-3)' }} />{t.category}</span>
                            )}
                      </td>
                      <td className="hide-mobile faint">{t.account_name}</td>
                      <td className={`amount ${t.type === 'transfer' ? 'muted' : signed >= 0 ? 'income' : ''}`}>
                        {t.type === 'transfer' ? money(t.amount_minor, t.currency) : money(signed, t.currency, { sign: true })}
                        {t.currency !== s?.currency && <div className="faint" style={{ fontSize: 11 }}>{money(t.base_amount_minor, s?.currency)}</div>}
                      </td>
                      <td>
                        <div className="row" style={{ gap: 2, justifyContent: 'flex-end' }}>
                          <Button size="sm" variant="ghost" icon={Pencil} aria-label="Edit" onClick={() => editTransaction(t)} />
                          <Button size="sm" variant="ghost" icon={Copy} aria-label="Duplicate" onClick={() => duplicate.mutate(t.id)} />
                          <Button size="sm" variant="ghost" icon={Trash2} aria-label="Delete" onClick={() => setConfirm({ txn: t })} />
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
        {list.data?.pages > 1 && (
          <div className="pagination">
            <span className="faint" style={{ fontSize: 13 }}>Page {page} of {list.data.pages}</span>
            <div className="row">
              <Button size="sm" disabled={page <= 1} onClick={() => update({ page: page - 1 }, false)}>Previous</Button>
              <Button size="sm" disabled={page >= list.data.pages} onClick={() => update({ page: page + 1 }, false)}>Next</Button>
            </div>
          </div>
        )}
      </Card>
      <Confirm
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title={confirm?.bulk ? `Delete ${selected.size} transactions?` : 'Delete this transaction?'}
        message={confirm?.bulk ? 'Balances, budgets and reports will update immediately. This cannot be undone.' : `${confirm?.txn?.description} · ${confirm?.txn ? money(confirm.txn.amount_minor, confirm.txn.currency) : ''}`}
        loading={bulk.isPending || remove.isPending}
        onConfirm={() => (confirm.bulk ? bulk.mutate({ ids: [...selected], action: 'delete' }) : remove.mutate(confirm.txn.id))}
      />
    </>
  )
}
