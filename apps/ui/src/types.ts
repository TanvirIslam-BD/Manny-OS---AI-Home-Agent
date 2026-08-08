export type RuntimeState =
  | 'BOOTING'
  | 'PAIRING'
  | 'IDLE'
  | 'PRESENT'
  | 'LISTENING'
  | 'TRANSCRIBING'
  | 'THINKING'
  | 'CONFIRMING'
  | 'SPEAKING'
  | 'DASHBOARD'
  | 'ALERT'
  | 'OFFLINE'
  | 'CAMERA_DISABLED'
  | 'MIC_MUTED'
  | 'ERROR'

export type PrivacyState =
  | 'PRIVATE_IDLE'
  | 'PRESENT_UNKNOWN'
  | 'PRESENT_TRUSTED'
  | 'MULTIPLE_PEOPLE'
  | 'PRIVACY_LOCKED'

export interface RuntimeSnapshot {
  state: RuntimeState
  privacy: PrivacyState
  connected: boolean
  presence: boolean
  people_count: number
  microphone_muted: boolean
  camera_enabled: boolean
  listening_enabled: boolean
  listening_available: boolean
  language: string
  status_message: string
  sequence: number
  updated_at: string
}

export interface PublicSettings {
  environment: string
  deviceId: string
  hardwareMode: string
  display: {
    width: number | null
    height: number | null
    rotation: number
    scale: number
  }
  cameraEnabled: boolean
  voice: {
    defaultLanguage: string
    loopEnabled: boolean
    loopAvailable: boolean
    captureSeconds: number
    vadThreshold: number
  }
  presence: {
    detector: string
    available: boolean
  }
}

export type MCPConnectionPhase =
  | 'mock'
  | 'disabled'
  | 'connecting'
  | 'auth_required'
  | 'connected'
  | 'degraded'
  | 'error'

export interface MCPStatus {
  phase: MCPConnectionPhase
  connected: boolean
  server_name: string
  protocol_version: string | null
  authorization_url: string | null
  discovered_tools: string[]
  allowed_tools: string[]
  detail: string
  checked_at: string
}

export interface AgentResponse {
  answer: string
  intent: string
  language: string
  tool_name: string | null
  data: Record<string, unknown> | null
  requires_confirmation: boolean
  requires_authentication: boolean
}

export interface FinanceDashboardData {
  budget: AgentResponse | null
  spending: AgentResponse | null
  refreshed_at: string
}

export interface VoiceResponse {
  transcript: string
  answer: string
  tool_name: string | null
  language: string
}

export type MannyEvent =
  | { type: 'system.state'; payload: RuntimeSnapshot }
  | { type: 'mcp.status'; payload: MCPStatus }
