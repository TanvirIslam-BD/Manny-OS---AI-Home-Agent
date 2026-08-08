import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import FinanceDashboard from './FinanceDashboard'
import type { FinanceDashboardData } from '../types'

const liveData: FinanceDashboardData = {
  refreshed_at: '2026-08-08T00:00:00Z',
  budget: {
    answer: 'Budget summary', intent: 'budget_status', language: 'en', tool_name: 'get_budget_status',
    requires_authentication: false, requires_confirmation: false,
    data: { currency: 'USD', budget: 1800, spent: 1240, remaining: 560, percent_used: 68.9 },
  },
  spending: {
    answer: 'Category summary', intent: 'category_spending', language: 'en', tool_name: 'summarize_expenses',
    requires_authentication: false, requires_confirmation: false,
    data: { currency: 'USD', categories: [{ name: 'Dining', amount: 458 }] },
  },
}

describe('FinanceDashboard', () => {
  it('masks MCP finance details for an unknown person', () => {
    render(<FinanceDashboard privacy="PRESENT_UNKNOWN" state="PRESENT" connected data={liveData} loading={false} error={null} onRefresh={vi.fn()} />)

    expect(screen.getByLabelText('Private information hidden')).toBeInTheDocument()
    expect(screen.queryByText(/560\.00/)).not.toBeInTheDocument()
  })

  it('renders validated MCP values instead of demo data', () => {
    render(<FinanceDashboard privacy="PRESENT_TRUSTED" state="DASHBOARD" connected data={liveData} loading={false} error={null} onRefresh={vi.fn()} />)

    expect(screen.getByLabelText('Money Copilot finance summary')).toBeInTheDocument()
    expect(screen.getByText(/560\.00/)).toBeInTheDocument()
    expect(screen.getByText('Dining')).toBeInTheDocument()
    expect(screen.getByText(/Live MCP data/)).toBeInTheDocument()
  })

  it('asks for MCP authorization instead of showing demo values while disconnected', () => {
    render(<FinanceDashboard privacy="PRESENT_TRUSTED" state="OFFLINE" connected={false} data={null} loading={false} error={null} onRefresh={vi.fn()} />)

    expect(screen.getByText('Connect Money Copilot')).toBeInTheDocument()
    expect(screen.queryByText(/560\.00/)).not.toBeInTheDocument()
  })
})
