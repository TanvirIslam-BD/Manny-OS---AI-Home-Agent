import { useEffect, useMemo, useState } from 'react'
import {
  connectEvents,
  connectMcp,
  getMcpStatus,
  getState,
  pushToTalk,
  setPresence,
  setSimulatorState,
} from './api/client'
import FinanceDashboard from './components/FinanceDashboard'
import { Icon } from './components/Icons'
import MannyFace from './components/MannyFace'
import type { MCPStatus, RuntimeSnapshot, RuntimeState } from './types'

const initialState: RuntimeSnapshot = {
  state: 'BOOTING',
  privacy: 'PRIVATE_IDLE',
  connected: true,
  presence: false,
  people_count: 0,
  microphone_muted: false,
  camera_enabled: true,
  status_message: 'Connecting to Manny Core',
  sequence: 0,
  updated_at: new Date().toISOString(),
}

const initialMcpStatus: MCPStatus = {
  phase: 'connecting',
  connected: false,
  server_name: 'Money Copilot MCP',
  protocol_version: null,
  authorization_url: null,
  discovered_tools: [],
  allowed_tools: [],
  detail: 'Checking Money Copilot connection',
  checked_at: new Date().toISOString(),
}

const SIMULATOR_STATES: RuntimeState[] = [
  'IDLE', 'PRESENT', 'LISTENING', 'THINKING', 'SPEAKING', 'DASHBOARD',
  'ALERT', 'OFFLINE', 'MIC_MUTED', 'CAMERA_DISABLED', 'ERROR',
]

const stateLabels: Partial<Record<RuntimeState, string>> = {
  IDLE: 'Idle', PRESENT: 'Present', LISTENING: 'Listening', THINKING: 'Thinking',
  SPEAKING: 'Speaking', DASHBOARD: 'Dashboard', ALERT: 'Alert', OFFLINE: 'Offline',
  MIC_MUTED: 'Mic muted', CAMERA_DISABLED: 'Camera off', ERROR: 'Error',
}

function App() {
  const [snapshot, setSnapshot] = useState(initialState)
  const [socketConnected, setSocketConnected] = useState(false)
  const [mcpStatus, setMcpStatus] = useState(initialMcpStatus)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    getState(controller.signal).then(setSnapshot).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(messageFrom(reason))
    })
    getMcpStatus(controller.signal).then(setMcpStatus).catch(() => undefined)
    const disconnect = connectEvents(
      (event) => {
        if (event.type === 'system.state') setSnapshot(event.payload)
        if (event.type === 'mcp.status') setMcpStatus(event.payload)
      },
      setSocketConnected,
    )
    const poll = window.setInterval(() => {
      getMcpStatus(controller.signal).then(setMcpStatus).catch(() => undefined)
    }, 4000)
    return () => {
      controller.abort()
      window.clearInterval(poll)
      disconnect()
    }
  }, [])

  const greeting = useMemo(() => {
    if (snapshot.state === 'OFFLINE') return 'Connection paused'
    if (snapshot.state === 'ALERT') return 'A quick heads-up'
    if (snapshot.state === 'PRESENT') return 'Welcome back'
    const hour = new Date().getHours()
    return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  }, [snapshot.state])

  async function run(action: () => Promise<RuntimeSnapshot>) {
    setBusy(true)
    setError(null)
    try {
      setSnapshot(await action())
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  async function authorizeMoneyCopilot() {
    setBusy(true)
    setError(null)
    try {
      const status = await connectMcp()
      setMcpStatus(status)
      if (status.authorization_url) window.location.assign(status.authorization_url)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="simulator-shell">
      <header className="brandbar">
        <div className="brandmark" aria-hidden="true"><span>M</span></div>
        <div>
          <strong>Manny Copilot</strong>
          <small>Money Copilot AI · Device simulator</small>
        </div>
        <div className={`core-status ${socketConnected ? 'core-status--online' : ''}`}>
          <i /> {socketConnected ? 'Core connected' : 'Core reconnecting'}
        </div>
        <div className={`core-status ${mcpStatus.connected ? 'core-status--online' : 'core-status--attention'}`}>
          <i /> {mcpStatus.connected ? 'Money connected' : 'Money setup'}
        </div>
      </header>

      <div className="workspace">
        <section className="device-stage" aria-label="Manny device display simulator">
          <div className={`device device--${snapshot.state.toLowerCase()}`}>
            <div className="device__halo" />
            <div className="device__bezel">
              <div className="screen">
                <header className="screen__status">
                  <div>
                    <span className="eyebrow">{greeting}</span>
                    <strong>{snapshot.status_message}</strong>
                  </div>
                  <div className="status-icons">
                    {!snapshot.camera_enabled && <Icon name="eyeOff" />}
                    {!snapshot.connected && <Icon name="wifiOff" />}
                    <span className={`privacy-dot privacy-dot--${snapshot.privacy.toLowerCase()}`} title={snapshot.privacy} />
                  </div>
                </header>

                <MannyFace state={snapshot.state} />
                <FinanceDashboard privacy={snapshot.privacy} state={snapshot.state} connected={mcpStatus.connected} />

                <button
                  className={`ask-button ${snapshot.state === 'LISTENING' ? 'ask-button--listening' : ''}`}
                  type="button"
                  disabled={busy || snapshot.microphone_muted}
                  onClick={() => void run(pushToTalk)}
                >
                  <Icon name="mic" />
                  <span>{snapshot.microphone_muted ? 'Microphone muted' : snapshot.state === 'LISTENING' ? 'Listening…' : 'Ask Manny'}</span>
                </button>

                <nav className="screen__nav" aria-label="Device navigation">
                  <button className="is-active" type="button"><Icon name="home" /><span>Home</span></button>
                  <button type="button"><Icon name="chart" /><span>Insights</span></button>
                  <button className="nav-orb" type="button" onClick={() => void run(pushToTalk)} aria-label="Talk to Manny"><span>M</span></button>
                  <button type="button"><Icon name="bell" /><span>Alerts</span></button>
                  <button type="button"><Icon name="gear" /><span>Settings</span></button>
                </nav>
              </div>
            </div>
            <div className="device__speaker"><span /><span /><span /><span /><span /><span /><span /></div>
            <div className="device__base-light" />
          </div>
        </section>

        <aside className="controls">
          <div className="controls__heading">
            <span className="eyebrow">Development controls</span>
            <h1>Bring Manny to life</h1>
            <p>Trigger every runtime expression without camera, microphone, or Raspberry Pi hardware.</p>
          </div>

          <section className="control-group">
            <div className="control-group__title"><span>Money Copilot MCP</span><small>{mcpStatus.phase.replaceAll('_', ' ')}</small></div>
            <div className={`mcp-connection mcp-connection--${mcpStatus.phase}`}>
              <div className="mcp-connection__signal"><i /><i /><i /></div>
              <div className="mcp-connection__copy">
                <strong>{mcpStatus.server_name}</strong>
                <p>{mcpStatus.detail}</p>
                {mcpStatus.connected && (
                  <small>{mcpStatus.discovered_tools.length} tools discovered · protocol {mcpStatus.protocol_version}</small>
                )}
              </div>
              {!mcpStatus.connected && mcpStatus.phase !== 'mock' && (
                <button type="button" disabled={busy || mcpStatus.phase === 'connecting'} onClick={() => void authorizeMoneyCopilot()}>
                  {mcpStatus.phase === 'connecting' ? 'Checking…' : 'Authorize'}
                </button>
              )}
            </div>
          </section>

          <section className="control-group">
            <div className="control-group__title"><span>Expression</span><small>{snapshot.state}</small></div>
            <div className="state-grid">
              {SIMULATOR_STATES.map((state) => (
                <button
                  className={state === snapshot.state ? 'is-selected' : ''}
                  key={state}
                  type="button"
                  disabled={busy}
                  onClick={() => void run(() => setSimulatorState(state))}
                >
                  <i />{stateLabels[state]}
                </button>
              ))}
            </div>
          </section>

          <section className="control-group">
            <div className="control-group__title"><span>Presence & privacy</span><small>{snapshot.privacy.replaceAll('_', ' ')}</small></div>
            <div className="segmented">
              {[0, 1, 2].map((count) => (
                <button
                  className={snapshot.people_count === count ? 'is-selected' : ''}
                  key={count}
                  type="button"
                  onClick={() => void run(() => setPresence(count))}
                >
                  {count === 0 ? 'Away' : count === 1 ? 'One person' : 'Group'}
                </button>
              ))}
            </div>
            <p className="privacy-note"><Icon name="shield" /> Financial values hide automatically when identity is unknown or multiple people are present.</p>
          </section>

          <section className="demo-note">
            <span>SIMULATOR FIXTURE</span>
            <p>The budget, spending, and payment values are fictional UI test data—not current financial facts.</p>
          </section>

          {error && <div className="error-banner" role="alert">{error}</div>}
        </aside>
      </div>
    </main>
  )
}

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : 'Manny Core is unavailable'
}

export default App
