import type { AgentResponse, FinanceDashboardData, MannyEvent, MCPStatus, MemoryStats, PublicSettings, Reminder, SecurityStatus, RuntimeSnapshot, RuntimeState, VoiceResponse } from '../types'

export async function askManny(text: string, language?: string): Promise<AgentResponse> {
  return postJson('/api/agent/query', { text, language })
}

export async function getFinanceDashboard(): Promise<FinanceDashboardData> {
  const [budget, spending] = await Promise.allSettled([
    askManny("How's my budget?"),
    askManny('Show my spending by category'),
  ])
  if (budget.status === 'rejected' && spending.status === 'rejected') {
    throw budget.reason instanceof Error ? budget.reason : new Error('Money data is unavailable')
  }
  return {
    budget: budget.status === 'fulfilled' ? budget.value : null,
    spending: spending.status === 'fulfilled' ? spending.value : null,
    refreshed_at: new Date().toISOString(),
  }
}

export async function simulateVoice(text: string, language?: string): Promise<VoiceResponse> {
  return postJson('/api/interaction/voice/simulate', { text, language })
}

/**
 * Ask the device to synthesise a reply this browser has no voice for.
 *
 * Returns WAV audio rather than JSON, so it cannot go through postJson. The
 * error detail is still JSON, and it is the useful part: it says whether the
 * device has no synthesiser configured or has one that failed.
 */
export async function synthesizeSpeech(text: string, language: string): Promise<Blob> {
  const response = await fetch('/api/voice/speak', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, language }),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Speech request failed: ${response.status}`)
  }
  return response.blob()
}

export async function getState(signal?: AbortSignal): Promise<RuntimeSnapshot> {
  const response = await fetch('/api/state', { signal })
  if (!response.ok) throw new Error(`State request failed: ${response.status}`)
  return response.json() as Promise<RuntimeSnapshot>
}

export async function setSimulatorState(state: RuntimeState): Promise<RuntimeSnapshot> {
  return postJson('/api/simulator/state', { state })
}

export async function setPresence(people_count: number): Promise<RuntimeSnapshot> {
  return postJson('/api/simulator/presence', { people_count })
}

export async function pushToTalk(): Promise<RuntimeSnapshot> {
  return postJson('/api/interaction/push-to-talk', {})
}

export async function getReminders(signal?: AbortSignal): Promise<Reminder[]> {
  const response = await fetch('/api/reminders', { signal })
  if (!response.ok) throw new Error(`Reminders request failed: ${response.status}`)
  return response.json() as Promise<Reminder[]>
}

export async function createReminder(title: string, due_at: string): Promise<Reminder> {
  return postJson('/api/reminders', { title, due_at })
}

export async function completeReminder(id: string): Promise<void> {
  const response = await fetch(`/api/reminders/${id}/complete`, { method: 'POST' })
  if (!response.ok) throw new Error(`Could not complete the reminder: ${response.status}`)
}

export async function setBrightness(value: number): Promise<{ brightness: number }> {
  return postJson('/api/device/brightness', { value })
}

export async function getSecurity(signal?: AbortSignal): Promise<SecurityStatus> {
  const response = await fetch('/api/security', { signal })
  if (!response.ok) throw new Error(`Security request failed: ${response.status}`)
  return response.json() as Promise<SecurityStatus>
}

export async function setPasscode(passcode: string, current_passcode?: string): Promise<SecurityStatus> {
  return postJson('/api/security/passcode', { passcode, current_passcode })
}

export async function unlockDevice(passcode: string): Promise<SecurityStatus> {
  return postJson('/api/security/unlock', { passcode })
}

export async function lockDevice(): Promise<SecurityStatus> {
  return postJson('/api/security/lock', {})
}

export async function getMemory(signal?: AbortSignal): Promise<MemoryStats> {
  const response = await fetch('/api/memory', { signal })
  if (!response.ok) throw new Error(`Memory request failed: ${response.status}`)
  return response.json() as Promise<MemoryStats>
}

export async function clearMemory(): Promise<MemoryStats> {
  return postJson('/api/memory/clear', {})
}

export async function cancelInteraction(): Promise<RuntimeSnapshot> {
  return postJson('/api/interaction/cancel', {})
}

export async function setListening(enabled: boolean): Promise<RuntimeSnapshot> {
  return postJson('/api/device/listening', { enabled })
}

export async function setDeviceLanguage(language: string): Promise<RuntimeSnapshot> {
  return postJson('/api/device/language', { language })
}

export async function getPublicSettings(signal?: AbortSignal): Promise<PublicSettings> {
  const response = await fetch('/api/settings/public', { signal })
  if (!response.ok) throw new Error(`Settings request failed: ${response.status}`)
  return response.json() as Promise<PublicSettings>
}

export async function getMcpStatus(signal?: AbortSignal): Promise<MCPStatus> {
  const response = await fetch('/api/mcp/status', { signal })
  if (!response.ok) throw new Error(`MCP status request failed: ${response.status}`)
  return response.json() as Promise<MCPStatus>
}

export async function connectMcp(): Promise<MCPStatus> {
  return postJson('/api/mcp/connect', {})
}

export async function switchMcpAccount(): Promise<MCPStatus> {
  return postJson('/api/mcp/switch-account', {})
}

export function connectEvents(
  onEvent: (event: MannyEvent) => void,
  onConnection: (connected: boolean) => void,
): () => void {
  let socket: WebSocket | null = null
  let retry: number | undefined
  let stopped = false

  const open = () => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    socket = new WebSocket(`${protocol}//${window.location.host}/api/ws`)
    socket.addEventListener('open', () => onConnection(true))
    socket.addEventListener('error', () => onConnection(false))
    socket.addEventListener('message', (message) => {
      try {
        onEvent(JSON.parse(message.data as string) as MannyEvent)
      } catch {
        onConnection(false)
      }
    })
    socket.addEventListener('close', () => {
      onConnection(false)
      if (!stopped) retry = window.setTimeout(open, 1500)
    })
  }

  open()
  return () => {
    stopped = true
    if (retry !== undefined) window.clearTimeout(retry)
    socket?.close()
  }
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null
    throw new Error(detail?.detail ?? `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}
