import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  connectEvents,
  connectMcp,
  askManny,
  getFinanceDashboard,
  getMcpStatus,
  getState,
  pushToTalk,
  setPresence,
  setSimulatorState,
  simulateVoice,
  switchMcpAccount,
} from './api/client'
import FinanceDashboard from './components/FinanceDashboard'
import CameraPresence from './components/CameraPresence'
import { Icon } from './components/Icons'
import MannyFace from './components/MannyFace'
import type { AgentResponse, FinanceDashboardData, MCPStatus, RuntimeSnapshot, RuntimeState } from './types'
import { listenOnce, speak, supportsBrowserVoice } from './voice/browser'

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
  'BOOTING', 'PAIRING', 'IDLE', 'PRESENT', 'LISTENING', 'TRANSCRIBING',
  'THINKING', 'CONFIRMING', 'SPEAKING', 'DASHBOARD', 'ALERT', 'OFFLINE',
  'MIC_MUTED', 'CAMERA_DISABLED', 'ERROR',
]

const stateLabels: Partial<Record<RuntimeState, string>> = {
  BOOTING: 'Booting', PAIRING: 'Pairing', IDLE: 'Idle', PRESENT: 'Present',
  LISTENING: 'Listening', TRANSCRIBING: 'Transcribing', THINKING: 'Thinking',
  CONFIRMING: 'Confirming', SPEAKING: 'Speaking', DASHBOARD: 'Dashboard', ALERT: 'Alert', OFFLINE: 'Offline',
  MIC_MUTED: 'Mic muted', CAMERA_DISABLED: 'Camera off', ERROR: 'Error',
}

const LANGUAGE_OPTIONS = [
  ['auto', 'Auto / Automatic'],
  ['en-US', 'English'],
  ['bn-BD', 'বাংলা'],
  ['hi-IN', 'हिन्दी'],
  ['zh-CN', '中文'],
  ['ja-JP', '日本語'],
  ['es-ES', 'Español'],
  ['fr-FR', 'Français'],
  ['de-DE', 'Deutsch'],
  ['ar', 'العربية'],
  ['pt-BR', 'Português'],
  ['ru-RU', 'Русский'],
  ['ko-KR', '한국어'],
] as const

type DeviceView = 'home' | 'insights' | 'alerts' | 'settings'

function App() {
  const [snapshot, setSnapshot] = useState(initialState)
  const [socketConnected, setSocketConnected] = useState(false)
  const [mcpStatus, setMcpStatus] = useState(initialMcpStatus)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [deviceView, setDeviceView] = useState<DeviceView>('home')
  const [question, setQuestion] = useState('How\'s my budget?')
  const [language, setLanguage] = useState('auto')
  const [agentResponse, setAgentResponse] = useState<AgentResponse | null>(null)
  const [financeData, setFinanceData] = useState<FinanceDashboardData | null>(null)
  const [financeLoading, setFinanceLoading] = useState(false)
  const [financeError, setFinanceError] = useState<string | null>(null)

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

  useEffect(() => {
    if (!mcpStatus.connected) return
    let active = true
    getFinanceDashboard()
      .then((data) => { if (active) setFinanceData(data) })
      .catch((reason: unknown) => { if (active) setFinanceError(messageFrom(reason)) })
      .finally(() => { if (active) setFinanceLoading(false) })
    return () => { active = false }
  }, [mcpStatus.connected])

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

  async function switchMoneyCopilotAccount() {
    const confirmed = window.confirm(
      'Switch Money Copilot account? Current authorization and cached finance data will be cleared. Local reminders and settings will be kept.',
    )
    if (!confirmed) return
    setBusy(true)
    setError(null)
    try {
      setFinanceData(null)
      setFinanceError(null)
      setAgentResponse(null)
      const status = await switchMcpAccount()
      setMcpStatus(status)
      if (status.authorization_url) window.location.assign(status.authorization_url)
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!question.trim()) return
    setBusy(true)
    setError(null)
    try {
      setAgentResponse(await askManny(
        question.trim(),
        language === 'auto' ? undefined : language,
      ))
    } catch (reason) {
      setError(messageFrom(reason))
    } finally {
      setBusy(false)
    }
  }

  async function startVoiceTurn() {
    setBusy(true)
    setError(null)
    try {
      await pushToTalk()
      const transcript = await listenOnce(language)
      setQuestion(transcript)
      const response = await simulateVoice(
        transcript,
        language === 'auto' ? undefined : language,
      )
      setAgentResponse({
        answer: response.answer,
        intent: 'voice',
        language: response.language,
        tool_name: response.tool_name,
        data: null,
        requires_confirmation: false,
        requires_authentication: false,
      })
      speak(response.answer, response.language)
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

                <div aria-live="polite" aria-atomic="true">
                  <MannyFace state={snapshot.state} />
                </div>
                <DevicePanel
                  view={deviceView}
                  snapshot={snapshot}
                  mcpConnected={mcpStatus.connected}
                  financeData={financeData}
                  financeLoading={financeLoading || (mcpStatus.connected && !financeData && !financeError)}
                  financeError={financeError}
                  refreshFinance={async () => {
                    setFinanceLoading(true)
                    setFinanceError(null)
                    try {
                      setFinanceData(await getFinanceDashboard())
                    } catch (reason) {
                      setFinanceError(messageFrom(reason))
                    } finally {
                      setFinanceLoading(false)
                    }
                  }}
                  busy={busy}
                  run={run}
                />

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
                  <button className={deviceView === 'home' ? 'is-active' : ''} aria-pressed={deviceView === 'home'} type="button" onClick={() => setDeviceView('home')}><Icon name="home" /><span>Home</span></button>
                  <button className={deviceView === 'insights' ? 'is-active' : ''} aria-pressed={deviceView === 'insights'} type="button" onClick={() => setDeviceView('insights')}><Icon name="chart" /><span>Insights</span></button>
                  <button className="nav-orb" type="button" onClick={() => void run(pushToTalk)} aria-label="Talk to Manny"><span>M</span></button>
                  <button className={deviceView === 'alerts' ? 'is-active' : ''} aria-pressed={deviceView === 'alerts'} type="button" onClick={() => setDeviceView('alerts')}><Icon name="bell" /><span>Alerts</span></button>
                  <button className={deviceView === 'settings' ? 'is-active' : ''} aria-pressed={deviceView === 'settings'} type="button" onClick={() => setDeviceView('settings')}><Icon name="gear" /><span>Settings</span></button>
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
              {mcpStatus.phase !== 'mock' && mcpStatus.phase !== 'auth_required' && (
                <button className="mcp-connection__switch" type="button" disabled={busy} onClick={() => void switchMoneyCopilotAccount()}>
                  {mcpStatus.connected ? 'Switch account' : 'Use another account'}
                </button>
              )}
            </div>
          </section>

          <section className="control-group">
            <div className="control-group__title"><span>Talk to Manny</span><small>typed simulation</small></div>
            <form className="agent-query" onSubmit={(event) => void submitQuestion(event)}>
              <div className="language-control">
                <label htmlFor="manny-language">Language</label>
                <select
                  id="manny-language"
                  value={language}
                  onChange={(event) => setLanguage(event.target.value)}
                >
                  {LANGUAGE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <label htmlFor="manny-question">Question</label>
              <div><input dir="auto" id="manny-question" value={question} maxLength={500} onChange={(event) => setQuestion(event.target.value)} /><button disabled={busy || !question.trim()} type="submit">Ask</button><button aria-label="Use desktop microphone" disabled={busy || !supportsBrowserVoice()} type="button" onClick={() => void startVoiceTurn()}><Icon name="mic" /></button></div>
            </form>
            {agentResponse && <div className="agent-answer" role="status"><strong>Manny · {agentResponse.language}</strong><p dir="auto">{agentResponse.answer}</p>{agentResponse.tool_name && <small>Verified via {agentResponse.tool_name}</small>}</div>}
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
            <CameraPresence onPeopleCount={async (count) => { await run(() => setPresence(count)) }} />
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
            <span>LIVE MCP DISPLAY</span>
            <p>The device cards use validated Money Copilot MCP results. Values hide automatically when privacy is locked.</p>
          </section>

          {error && <div className="error-banner" role="alert">{error}</div>}
        </aside>
      </div>
    </main>
  )
}

export function DevicePanel({
  view,
  snapshot,
  mcpConnected,
  financeData,
  financeLoading,
  financeError,
  refreshFinance,
  busy,
  run,
}: {
  view: DeviceView
  snapshot: RuntimeSnapshot
  mcpConnected: boolean
  financeData: FinanceDashboardData | null
  financeLoading: boolean
  financeError: string | null
  refreshFinance: () => Promise<void>
  busy: boolean
  run: (action: () => Promise<RuntimeSnapshot>) => Promise<void>
}) {
  if (snapshot.state === 'PAIRING') {
    return <section className="device-panel" aria-label="Pair Manny"><span className="eyebrow">Secure pairing</span><strong>Connect your Money Copilot account</strong><p>Authorize from the setup panel. Manny never displays or stores your password.</p><code>PAIR-MANNY</code></section>
  }
  if (snapshot.state === 'CONFIRMING') {
    return <section className="device-panel" aria-label="Confirm action"><span className="eyebrow">Confirmation required</span><strong>Create this local reminder?</strong><p>Review your credit card bill Friday at 7:00 PM.</p><div className="device-panel__actions"><button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState('SPEAKING'))}>Confirm</button><button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState('IDLE'))}>Cancel</button></div></section>
  }
  if (view === 'settings') {
    return <section className="device-panel" aria-label="Manny settings"><span className="eyebrow">Privacy controls</span><strong>Device settings</strong><button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState(snapshot.microphone_muted ? 'IDLE' : 'MIC_MUTED'))}>{snapshot.microphone_muted ? 'Unmute microphone' : 'Mute microphone'}</button><button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState(snapshot.camera_enabled ? 'CAMERA_DISABLED' : 'IDLE'))}>{snapshot.camera_enabled ? 'Disable camera' : 'Enable camera'}</button></section>
  }
  if (view === 'alerts') {
    return <section className="device-panel" aria-label="Money alerts"><span className="eyebrow">Alerts</span><strong>Spending alerts</strong><p>Verified alerts appear here and stay hidden when privacy is locked or multiple people are nearby.</p></section>
  }
  return <FinanceDashboard privacy={snapshot.privacy} state={snapshot.state} connected={mcpConnected} data={financeData} loading={financeLoading} error={financeError} onRefresh={refreshFinance} />
}

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : 'Manny Core is unavailable'
}

export default App
