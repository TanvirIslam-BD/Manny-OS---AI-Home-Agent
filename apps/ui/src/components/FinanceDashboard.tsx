import { Icon } from './Icons'
import type { PrivacyState, RuntimeState } from '../types'

const DEMO = {
  budget: '$560',
  spent: '$1,240',
  dining: '92%',
  payment: '$15.49',
  synced: '2 min ago',
}

export default function FinanceDashboard({
  privacy,
  state,
  connected,
}: {
  privacy: PrivacyState
  state: RuntimeState
  connected: boolean
}) {
  const masked = privacy === 'MULTIPLE_PEOPLE' || privacy === 'PRIVACY_LOCKED' || privacy === 'PRESENT_UNKNOWN'
  const amount = (value: string) => (masked ? '••••' : value)

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

  return (
    <section className="cards" aria-label="Demo finance summary">
      <article className="card card--budget">
        <header><span>Budget left</span><small>68.9% used</small></header>
        <strong>{amount(DEMO.budget)}</strong>
        <div className="progress"><span /></div>
      </article>
      <article className={`card card--alert ${state === 'ALERT' ? 'card--pulse' : ''}`}>
        <header><span>Dining alert</span><small>near limit</small></header>
        <strong>{DEMO.dining}</strong>
        <p>of category budget</p>
      </article>
      <article className="card card--payment">
        <header><span>Upcoming</span><small>tomorrow</small></header>
        <strong>Netflix</strong>
        <p>{amount(DEMO.payment)}</p>
      </article>
      <article className="card card--spend">
        <header><span>Monthly spend</span><small>+8%</small></header>
        <strong>{amount(DEMO.spent)}</strong>
        <svg className="spark" viewBox="0 0 100 32" aria-hidden="true">
          <path d="M2 27 18 24 31 28 46 16 58 20 72 8 84 13 98 3" />
        </svg>
      </article>
      <div className={`sync ${connected ? '' : 'sync--offline'}`}>
        {connected ? <span className="sync__dot" /> : <Icon name="wifiOff" />}
        {connected ? `Demo data · synced ${DEMO.synced}` : 'Offline · cached demo data'}
      </div>
    </section>
  )
}
