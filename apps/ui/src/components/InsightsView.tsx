import type { FinanceDashboardData, PrivacyState } from '../types'

type FinanceRecord = Record<string, unknown>

function record(value: unknown): FinanceRecord {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as FinanceRecord)
    : {}
}

function money(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(value)
  } catch {
    return `${currency} ${Math.round(value)}`
  }
}

export default function InsightsView({
  privacy,
  data,
}: {
  privacy: PrivacyState
  data: FinanceDashboardData | null
}) {
  if (privacy === 'MULTIPLE_PEOPLE' || privacy === 'PRIVACY_LOCKED' || privacy === 'PRESENT_UNKNOWN') {
    return (
      <section className="device-panel" aria-label="Insights hidden">
        <span className="eyebrow">Insights</span>
        <strong>Hidden while others are nearby</strong>
        <p>Unlock with your passcode to see your spending breakdown.</p>
      </section>
    )
  }

  const spending = record(data?.spending?.data)
  const currency = typeof spending.currency === 'string' ? spending.currency : 'USD'
  const raw = Array.isArray(spending.categories) ? spending.categories : []
  const categories = raw
    .flatMap((item) => {
      const entry = record(item)
      const name = typeof entry.name === 'string' ? entry.name : null
      const amount = typeof entry.amount === 'number' ? entry.amount : Number(entry.amount)
      return name && Number.isFinite(amount) && amount > 0 ? [{ name, amount }] : []
    })
    .sort((a, b) => b.amount - a.amount)

  if (categories.length === 0) {
    return (
      <section className="device-panel" aria-label="Insights">
        <span className="eyebrow">Insights</span>
        <strong>No spending breakdown yet</strong>
        <p>Connect Money Copilot and ask about your spending to populate this view.</p>
      </section>
    )
  }

  const top = categories.slice(0, 6)
  const total = categories.reduce((sum, item) => sum + item.amount, 0)
  const excluded = Array.isArray(spending.excluded_categories) ? spending.excluded_categories : []
  const others = record(spending.other_currency_totals)

  return (
    <section className="insights" aria-label="Spending insights">
      <header>
        <span className="eyebrow">This period</span>
        <strong>{money(total, currency)}</strong>
      </header>
      <ol className="insights__list">
        {top.map((item) => (
          <li key={item.name}>
            <div className="insights__row">
              <span>{item.name}</span>
              <small>{money(item.amount, currency)}</small>
            </div>
            <div className="insights__bar">
              <span style={{ width: `${Math.max(3, (item.amount / top[0].amount) * 100)}%` }} />
            </div>
            <em>{((item.amount / total) * 100).toFixed(0)}%</em>
          </li>
        ))}
      </ol>
      {excluded.length > 0 && Object.keys(others).length > 0 && (
        <p className="insights__note">
          Excludes {excluded.length} categories recorded in {Object.keys(others).join(', ')}.
        </p>
      )}
    </section>
  )
}
