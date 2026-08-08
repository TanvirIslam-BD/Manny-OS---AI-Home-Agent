import { Icon } from './Icons'
import type { FinanceDashboardData, PrivacyState, RuntimeState } from '../types'

type FinanceRecord = Record<string, unknown>

export default function FinanceDashboard({
  privacy,
  state,
  connected,
  data,
  loading,
  error,
  onRefresh,
}: {
  privacy: PrivacyState
  state: RuntimeState
  connected: boolean
  data: FinanceDashboardData | null
  loading: boolean
  error: string | null
  onRefresh: () => Promise<void>
}) {
  const masked = privacy === 'MULTIPLE_PEOPLE' || privacy === 'PRIVACY_LOCKED' || privacy === 'PRESENT_UNKNOWN'

  if (masked) {
    return (
      <section className="privacy-card" aria-label="Private information hidden">
        <div className="privacy-card__icon"><Icon name="lock" /></div>
        <div>
          <span>Private view</span>
          <strong>Financial details are hidden</strong>
          <p>{privacy === 'MULTIPLE_PEOPLE' ? 'Multiple people detected nearby.' : 'Unlock a trusted session to continue.'}</p>
        </div>
      </section>
    )
  }

  if (!connected) {
    return <StatusPanel title="Connect Money Copilot" detail="Authorize the MCP server to show verified financial data." />
  }
  if (loading && !data) {
    return <StatusPanel title="Loading your money data" detail="Manny is securely requesting budget and spending summaries." />
  }
  if (!data) {
    return <StatusPanel title="Money data unavailable" detail={error ?? 'No verified MCP result is available yet.'} retry={onRefresh} />
  }

  const budget = record(data.budget?.data)
  const spending = record(data.spending?.data)
  const currency = textValue(budget.currency) ?? textValue(spending.currency) ?? 'USD'
  const remaining = numberValue(budget.remaining)
  const spent = numberValue(budget.spent) ?? categoryTotal(spending.categories)
  const percentUsed = numberValue(budget.percent_used)
  const topCategory = highestCategory(spending.categories)
  const cached = Boolean(record(budget._cache).fetched_at || record(spending._cache).fetched_at)
  const syncTime = new Date(data.refreshed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

  return (
    <section className="cards" aria-label="Money Copilot finance summary">
      <article className="card card--budget">
        <header><span>Budget left</span><small>{percentUsed === null ? 'MCP verified' : `${percentUsed.toFixed(1)}% used`}</small></header>
        <strong>{remaining === null ? 'Unavailable' : money(remaining, currency)}</strong>
        <div className="progress"><span style={{ width: `${Math.min(Math.max(percentUsed ?? 0, 0), 100)}%` }} /></div>
      </article>
      <article className={`card card--alert ${state === 'ALERT' ? 'card--pulse' : ''}`}>
        <header><span>Top category</span><small>current period</small></header>
        <strong>{topCategory?.name ?? 'Unavailable'}</strong>
        <p>{topCategory ? money(topCategory.amount, currency) : 'No category summary'}</p>
      </article>
      <article className="card card--payment">
        <header>
          <span>Data source</span>
          <button
            className="card__refresh"
            type="button"
            disabled={loading}
            aria-label="Refresh money data"
            onClick={() => void onRefresh()}
          >
            {loading ? '…' : cached ? `cached ${syncTime}` : `live ${syncTime}`}
          </button>
        </header>
        <strong>Money Copilot</strong>
        <p>{data.budget?.tool_name ?? data.spending?.tool_name ?? 'MCP verified'}</p>
      </article>
      <article className="card card--spend">
        <header><span>Period spend</span><small>MCP total</small></header>
        <strong>{spent === null ? 'Unavailable' : money(spent, currency)}</strong>
        <svg className="spark" viewBox="0 0 100 32" aria-hidden="true">
          <path d="M2 27 18 24 31 28 46 16 58 20 72 8 84 13 98 3" />
        </svg>
      </article>

    </section>
  )
}

function StatusPanel({ title, detail, retry }: { title: string; detail: string; retry?: () => Promise<void> }) {
  return <section className="device-panel" aria-label={title}><span className="eyebrow">Money Copilot MCP</span><strong>{title}</strong><p>{detail}</p>{retry && <button type="button" onClick={() => void retry()}>Try again</button>}</section>
}

function record(value: unknown): FinanceRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as FinanceRecord : {}
}

function numberValue(value: unknown): number | null {
  const result = typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : Number.NaN
  return Number.isFinite(result) ? result : null
}

function textValue(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

function highestCategory(value: unknown): { name: string; amount: number } | null {
  if (!Array.isArray(value)) return null
  const categories = value.flatMap((item) => {
    const candidate = record(item)
    const name = textValue(candidate.name)
    const amount = numberValue(candidate.amount)
    return name !== null && amount !== null ? [{ name, amount }] : []
  })
  return categories.reduce<{ name: string; amount: number } | null>((top, item) => !top || item.amount > top.amount ? item : top, null)
}

function categoryTotal(value: unknown): number | null {
  if (!Array.isArray(value)) return null
  const amounts = value.map((item) => numberValue(record(item).amount)).filter((amount): amount is number => amount !== null)
  return amounts.length ? amounts.reduce((total, amount) => total + amount, 0) : null
}

function money(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(value)
  } catch {
    return `${currency} ${value.toFixed(2)}`
  }
}
