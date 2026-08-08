import { useEffect, useMemo, useState, type FormEvent } from 'react'
import {
  connectEvents,
  connectMcp,
  askManny,
  getFinanceDashboard,
  getMcpStatus,
  getState,
  pushToTalk,
  cancelInteraction,
  setPresence,
  setSimulatorState,
  simulateVoice,
  switchMcpAccount,
  setListening,
  setDeviceLanguage,
  getPublicSettings,
  getMemory,
  clearMemory,
  getSecurity,
  getReminders,
} from './api/client'
import FinanceDashboard from './components/FinanceDashboard'
import CameraPresence from './components/CameraPresence'
import { Icon } from './components/Icons'
import MannyFace from './components/MannyFace'
import PasscodePanel from './components/PasscodePanel'
import InsightsView from './components/InsightsView'
import AlertsView from './components/AlertsView'
import type { AgentResponse, FinanceDashboardData, MCPStatus, MemoryStats, PublicSettings, Reminder, SecurityStatus, RuntimeSnapshot, RuntimeState } from './types'
import { listenOnce, speak, supportsBrowserVoice } from './voice/browser'

const initialState: RuntimeSnapshot = {
  state: 'BOOTING',
  privacy: 'PRIVATE_IDLE',
  connected: true,
  presence: false,
  people_count: 0,
  microphone_muted: false,
  camera_enabled: true,
  listening_enabled: false,
  listening_available: false,
  language: 'auto',
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
  const [agentResponse, setAgentResponse] = useState<AgentResponse | null>(null)
  const [financeData, setFinanceData] = useState<FinanceDashboardData | null>(null)
  const [financeLoading, setFinanceLoading] = useState(false)
  const [financeError, setFinanceError] = useState<string | null>(null)
  const [settings, setSettings] = useState<PublicSettings | null>(null)
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const [memory, setMemory] = useState<MemoryStats | null>(null)
  const [security, setSecurity] = useState<SecurityStatus | null>(null)
  const [reminders, setReminders] = useState<Reminder[]>([])

  useEffect(() => {
    const controller = new AbortController()
    getState(controller.signal).then(setSnapshot).catch((reason: unknown) => {
      if (!controller.signal.aborted) setError(messageFrom(reason))
    })
    getMcpStatus(controller.signal).then(setMcpStatus).catch(() => undefined)
    getPublicSettings(controller.signal).then(setSettings).catch(() => undefined)
    getMemory(controller.signal).then(setMemory).catch(() => undefined)
    getSecurity(controller.signal).then(setSecurity).catch(() => undefined)
    getReminders(controller.signal).then(setReminders).catch(() => undefined)
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

  const language = snapshot.language
  // A successful callback flips the status, which retires the webview on its own.
  const pendingAuthUrl = mcpStatus.connected ? null : authUrl

  // On the Pi the app *is* the panel, so the simulated chassis is dropped and the
  // screen fills the viewport. The device geometry drives the screen-to-body ratio
  // in both modes, so the simulator matches the panel that ships.
  const kiosk = useMemo(() => {
    const forced = new URLSearchParams(window.location.search).get('kiosk')
    if (forced !== null) return forced !== '0'
    return settings?.environment === 'raspberrypi' || settings?.environment === 'production'
  }, [settings?.environment])

  const displayRatio = useMemo(() => {
    const width = settings?.display.width ?? 480
    const height = settings?.display.height ?? 480
    return width > 0 && height > 0 ? width / height : 1
  }, [settings?.display.width, settings?.display.height])

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
      // The device has no browser to hand off to, so authorization happens in an
      // embedded webview on the panel itself.
      if (status.authorization_url) setAuthUrl(status.authorization_url)
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
      if (status.authorization_url) setAuthUrl(status.authorization_url)
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

  // Browser speech recognition cannot auto-detect: it needs one concrete tag.
  // "Auto detect" is real on the device (whisper.cpp), so here we resolve it to
  // the language Manny last replied in, then the device default, then the locale.
  const listeningLanguage =
    language !== 'auto'
      ? language
      : agentResponse?.language && agentResponse.language !== 'en'
        ? agentResponse.language
        : settings?.voice.defaultLanguage && settings.voice.defaultLanguage !== 'auto'
          ? settings.voice.defaultLanguage
          : navigator.language

  async function startVoiceTurn() {
    if (!supportsBrowserVoice()) {
      setError('This browser cannot capture speech. Use the typed question box, or run Manny on the device.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await pushToTalk()
      const transcript = await listenOnce(listeningLanguage)
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
      setSnapshot(await cancelInteraction().catch(() => snapshot))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main
      className={`simulator-shell ${kiosk ? 'simulator-shell--kiosk' : ''}`}
      style={{ ["--display-ratio" as string]: `${displayRatio}` }}
    >
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
            <span className="device__key device__key--left" aria-hidden="true" />
            <span className="device__key device__key--right" aria-hidden="true" />
            <div className="device__bezel">
              <div className="screen">
                <span className="screen__camera" aria-hidden="true" />
                <header className="screen__status">
                  <div className="screen__bubble">
                    <span className="eyebrow">{greeting}</span>
                    <strong>{snapshot.status_message}</strong>
                  </div>
                  <div className="screen__actions">
                    <button
                      className={`mic-orb ${snapshot.state === 'LISTENING' ? 'mic-orb--live' : ''}`}
                      type="button"
                      disabled={busy || snapshot.microphone_muted}
                      aria-label={snapshot.microphone_muted ? 'Microphone muted' : 'Talk to Manny'}
                      onClick={() => void startVoiceTurn()}
                    >
                      <Icon name="mic" />
                    </button>
                    <div className="status-icons">
                      {!snapshot.camera_enabled && <Icon name="eyeOff" />}
                      {!snapshot.connected && <Icon name="wifiOff" />}
                      <span className={`privacy-dot privacy-dot--${snapshot.privacy.toLowerCase()}`} title={snapshot.privacy} />
                    </div>
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
                  settings={settings}
                  mcpStatus={mcpStatus}
                  onConnectMcp={() => void authorizeMoneyCopilot()}
                  memory={memory}
                  security={security}
                  reminders={reminders}
                  onRemindersChanged={async () => setReminders(await getReminders())}
                  onSecurityChange={async (status) => {
                    setSecurity(status)
                    setSnapshot(await getState())
                  }}
                  onClearMemory={async () => {
                    if (!window.confirm('Clear everything Manny remembers from your conversations? Reminders and settings are kept.')) return
                    try {
                      setMemory(await clearMemory())
                    } catch (reason) {
                      setError(messageFrom(reason))
                    }
                  }}
                />

                <button
                  className={`ask-button ${snapshot.state === 'LISTENING' ? 'ask-button--listening' : ''}`}
                  type="button"
                  disabled={busy || snapshot.microphone_muted}
                  onClick={() => void startVoiceTurn()}
                >
                  <Icon name="mic" />
                  <span>{snapshot.microphone_muted ? 'Microphone muted' : snapshot.state === 'LISTENING' ? 'Listening…' : 'Ask Manny'}</span>
                </button>

                {pendingAuthUrl && (
                  <div className="webview" role="dialog" aria-label="Authorize Money Copilot">
                    <header>
                      <span>Money Copilot sign-in</span>
                      <button type="button" onClick={() => setAuthUrl(null)} aria-label="Close sign-in">✕</button>
                    </header>
                    <iframe title="Money Copilot authorization" src={pendingAuthUrl} />
                    <footer>
                      If the provider blocks embedding, <a href={pendingAuthUrl} rel="noreferrer">open it in a browser</a>.
                    </footer>
                  </div>
                )}

                {error && (
                  <div className="screen__toast" role="alert">
                    <span>{error}</span>
                    <button type="button" onClick={() => setError(null)} aria-label="Dismiss">✕</button>
                  </div>
                )}

                <nav className="screen__nav" aria-label="Device navigation">
                  <button className={deviceView === 'home' ? 'is-active' : ''} aria-pressed={deviceView === 'home'} type="button" onClick={() => setDeviceView('home')}><Icon name="home" /><span>Home</span></button>
                  <button className={deviceView === 'insights' ? 'is-active' : ''} aria-pressed={deviceView === 'insights'} type="button" onClick={() => setDeviceView('insights')}><Icon name="chart" /><span>Insights</span></button>
                  <button className="nav-orb" type="button" disabled={busy || snapshot.microphone_muted} onClick={() => void startVoiceTurn()} aria-label="Talk to Manny"><span>M</span></button>
                  <button className={deviceView === 'alerts' ? 'is-active' : ''} aria-pressed={deviceView === 'alerts'} type="button" onClick={() => setDeviceView('alerts')}><Icon name="bell" /><span>Alerts</span></button>
                  <button className={deviceView === 'settings' ? 'is-active' : ''} aria-pressed={deviceView === 'settings'} type="button" onClick={() => setDeviceView('settings')}><Icon name="gear" /><span>Settings</span></button>
                </nav>
              </div>
            </div>
            <div className="device__badge" aria-hidden="true"><span>M</span></div>
            <div className="device__base-light" />
            <div className="device__grille" aria-hidden="true" />
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
                  onChange={(event) => void run(() => setDeviceLanguage(event.target.value))}
                >
                  {LANGUAGE_OPTIONS.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </div>
              <label htmlFor="manny-question">Question</label>
              <div><input dir="auto" id="manny-question" value={question} maxLength={500} onChange={(event) => setQuestion(event.target.value)} /><button disabled={busy || !question.trim()} type="submit">Ask</button><button aria-label="Use desktop microphone" disabled={busy || !supportsBrowserVoice()} type="button" onClick={() => void startVoiceTurn()}><Icon name="mic" /></button></div>
            </form>
            <p className="agent-query__hint">
              {language === 'auto'
                ? `Auto detect is on-device only — the browser microphone will listen in ${listeningLanguage}. Pick a language to change it.`
                : `The microphone will listen in ${listeningLanguage}.`}
            </p>
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
  settings,
  mcpStatus,
  onConnectMcp,
  memory,
  onClearMemory,
  security,
  onSecurityChange,
  reminders,
  onRemindersChanged,
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
  settings?: PublicSettings | null
  mcpStatus?: MCPStatus
  onConnectMcp?: () => void
  memory?: MemoryStats | null
  onClearMemory?: () => Promise<void>
  security?: SecurityStatus | null
  onSecurityChange?: (status: SecurityStatus) => void
  reminders?: Reminder[]
  onRemindersChanged?: () => Promise<void>
}) {
  if (snapshot.state === 'PAIRING') {
    return <section className="device-panel" aria-label="Pair Manny"><span className="eyebrow">Secure pairing</span><strong>Connect your Money Copilot account</strong><p>Authorize from the setup panel. Manny never displays or stores your password.</p><code>PAIR-MANNY</code></section>
  }
  if (snapshot.state === 'CONFIRMING') {
    return <section className="device-panel" aria-label="Confirm action"><span className="eyebrow">Confirmation required</span><strong>Create this local reminder?</strong><p>Review your credit card bill Friday at 7:00 PM.</p><div className="device-panel__actions"><button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState('SPEAKING'))}>Confirm</button><button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState('IDLE'))}>Cancel</button></div></section>
  }
  if (view === 'settings') {
    const voice = settings?.voice
    const presence = settings?.presence
    return (
      <section className="device-panel" aria-label="Manny settings">
        <span className="eyebrow">Privacy controls</span>
        <strong>Device settings</strong>
        <button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState(snapshot.microphone_muted ? 'IDLE' : 'MIC_MUTED'))}>{snapshot.microphone_muted ? 'Unmute microphone' : 'Mute microphone'}</button>
        <button disabled={busy} type="button" onClick={() => void run(() => setSimulatorState(snapshot.camera_enabled ? 'CAMERA_DISABLED' : 'IDLE'))}>{snapshot.camera_enabled ? 'Disable camera' : 'Enable camera'}</button>
        <button
          disabled={busy || !snapshot.listening_available}
          type="button"
          title={snapshot.listening_available ? undefined : 'Requires a real microphone'}
          onClick={() => void run(() => setListening(!snapshot.listening_enabled))}
        >
          {snapshot.listening_enabled ? 'Stop always listening' : 'Start always listening'}
        </button>
        {mcpStatus && (
          <button
            className="device-settings__mcp"
            disabled={busy || mcpStatus.phase === 'mock'}
            type="button"
            onClick={() => onConnectMcp?.()}
          >
            <span>{mcpStatus.connected ? 'Reconnect Money Copilot' : 'Connect Money Copilot'}</span>
            <small>{mcpStatus.detail}</small>
          </button>
        )}
        <label className="device-settings__language">
          <span>Language</span>
          <select
            value={snapshot.language}
            disabled={busy}
            onChange={(event) => void run(() => setDeviceLanguage(event.target.value))}
          >
            <option value="auto">Auto detect</option>
            {LANGUAGE_OPTIONS.filter(([value]) => value !== 'auto').map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        {security && onSecurityChange && (
          <PasscodePanel security={security} busy={busy} onChange={onSecurityChange} />
        )}
        {memory && (
          <button
            className="device-settings__mcp"
            disabled={busy || memory.entries === 0}
            type="button"
            onClick={() => void onClearMemory?.()}
          >
            <span>{memory.entries === 0 ? 'Memory is empty' : 'Clear what Manny remembers'}</span>
            <small>
              {memory.entries} of {memory.limit} remembered
              {memory.entries >= memory.limit ? ' · full, oldest are dropped' : ''}
            </small>
          </button>
        )}
        <dl className="device-settings__facts">
          <div>
            <dt>Always listening</dt>
            <dd>{!snapshot.listening_available ? 'Unavailable on this device' : snapshot.listening_enabled ? 'On' : 'Off'}</dd>
          </div>
          {voice && (
            <div>
              <dt>Listen window</dt>
              <dd>{voice.captureSeconds}s · speech threshold {voice.vadThreshold}</dd>
            </div>
          )}
          {presence && (
            <div>
              <dt>Presence detection</dt>
              <dd>{presence.available ? presence.detector : 'Not configured'}</dd>
            </div>
          )}
        </dl>
      </section>
    )
  }
  if (view === 'alerts') {
    return (
      <AlertsView
        reminders={reminders ?? []}
        busy={busy}
        onChanged={onRemindersChanged ?? (async () => undefined)}
      />
    )
  }
  if (view === 'insights') {
    return <InsightsView privacy={snapshot.privacy} data={financeData} />
  }
  return <FinanceDashboard privacy={snapshot.privacy} state={snapshot.state} connected={mcpConnected} data={financeData} loading={financeLoading} error={financeError} onRefresh={refreshFinance} />
}

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : 'Manny Core is unavailable'
}

export default App
