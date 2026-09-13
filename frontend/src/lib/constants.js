export const API = '/api'

export const categories = [
  'Groceries',
  'Eating out',
  'Rent & utilities',
  'Transport',
  'Shopping',
  'Health',
  'Investments',
  'Subscriptions',
  'Education',
  'Family',
  'Other',
]

export const paymentMethods = ['UPI', 'Debit card', 'Credit card', 'Cash', 'Net banking', 'Bank transfer', 'Auto-debit']

export const kinds = [
  { id: 'expense', label: 'Expense' },
  { id: 'income', label: 'Income' },
  { id: 'investment', label: 'Investment' },
]

export const kindDetails = {
  expense: {
    eyebrow: 'EVERYDAY SPEND',
    title: 'Capture an expense',
    hint: 'Track the little things and the big commitments.',
    placeholder: 'e.g. Dinner at Swiggy',
    accent: 'expense-mode',
  },
  income: {
    eyebrow: 'MONEY IN',
    title: 'Record income',
    hint: 'Salary, freelance work, refunds, or any money received.',
    placeholder: 'e.g. September salary',
    accent: 'income-mode',
  },
  investment: {
    eyebrow: 'BUILDING WEALTH',
    title: 'Log an investment',
    hint: 'Keep SIPs, stocks, mutual funds, and deposits visible.',
    placeholder: 'e.g. Nifty index SIP',
    accent: 'investment-mode',
  },
}

export const colors = ['#8ae6ff', '#b29bff', '#7ef0c2', '#ffd8a8', '#ff8fab', '#70d6ff', '#f7b267', '#95d5b2', '#c8b6ff', '#a8dadc', '#ff9d66']

export const accountTypes = ['savings', 'current', 'cash', 'credit', 'wallet', 'investment']

export const navItems = [
  { id: 'overview', label: 'Overview', icon: '⌂', hint: 'Dashboard' },
  { id: 'autosync', label: 'Auto-Sync & UPI', icon: '⚡', hint: 'Live Sync' },
  { id: 'transactions', label: 'Transactions', icon: '↕', hint: 'Ledger' },
  { id: 'accounts', label: 'Accounts', icon: '▣', hint: 'Wallets' },
  { id: 'investments', label: 'Investments', icon: '◈', hint: 'Portfolio' },
  { id: 'budgets', label: 'Budgets', icon: '◒', hint: 'Limits' },
  { id: 'bills', label: 'Bills', icon: '◷', hint: 'Due dates' },
  { id: 'insights', label: 'Insights', icon: '◉', hint: 'Patterns' },
  { id: 'goals', label: 'Goals', icon: '◎', hint: 'Targets' },
]

