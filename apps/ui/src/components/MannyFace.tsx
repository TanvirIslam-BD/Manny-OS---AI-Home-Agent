import type { RuntimeState } from '../types'

const ACTIVE_STATES = new Set<RuntimeState>(['LISTENING', 'TRANSCRIBING', 'THINKING', 'SPEAKING'])

export default function MannyFace({ state }: { state: RuntimeState }) {
  const expression =
    state === 'ALERT' || state === 'ERROR'
      ? 'concerned'
      : state === 'SPEAKING'
        ? 'speaking'
        : state === 'THINKING' || state === 'TRANSCRIBING'
          ? 'thinking'
          : state === 'LISTENING'
            ? 'listening'
            : 'calm'

  return (
    <div className={`face face--${expression}`} aria-label={`Manny is ${state.toLowerCase()}`}>
      <div className={`wave ${ACTIVE_STATES.has(state) ? 'wave--active' : ''}`} aria-hidden="true">
        {[8, 15, 24, 12, 20, 30, 18, 10, 25, 14, 8, 19, 27, 11, 16].map((height, index) => (
          <i key={index} style={{ height }} />
        ))}
      </div>
      <div className="face__ambient" />
      <div className="eye eye--left"><span /></div>
      <div className="eye eye--right"><span /></div>
      <div className="mouth"><span /></div>
    </div>
  )
}
