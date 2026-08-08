import type { MannyEvent, MCPStatus, RuntimeSnapshot, RuntimeState } from '../types'

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

export async function getMcpStatus(signal?: AbortSignal): Promise<MCPStatus> {
  const response = await fetch('/api/mcp/status', { signal })
  if (!response.ok) throw new Error(`MCP status request failed: ${response.status}`)
  return response.json() as Promise<MCPStatus>
}

export async function connectMcp(): Promise<MCPStatus> {
  return postJson('/api/mcp/connect', {})
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
