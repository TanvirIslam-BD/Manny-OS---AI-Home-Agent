import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DevicePanel } from './App'
import type { RuntimeSnapshot, RuntimeState } from './types'

const financeProps = {
  financeData: null,
  financeLoading: false,
  financeError: null,
  refreshFinance: vi.fn().mockResolvedValue(undefined),
}

function snapshot(state: RuntimeState): RuntimeSnapshot {
  return {
    state,
    privacy: 'PRESENT_TRUSTED',
    connected: true,
    presence: true,
    people_count: 1,
    microphone_muted: false,
    camera_enabled: true,
    status_message: state,
    sequence: 1,
    updated_at: new Date(0).toISOString(),
  }
}

describe('DevicePanel', () => {
  it('renders the account pairing surface', () => {
    render(<DevicePanel view="home" snapshot={snapshot('PAIRING')} mcpConnected={false} busy={false} run={vi.fn()} {...financeProps} />)

    expect(screen.getByRole('region', { name: 'Pair Manny' })).toBeInTheDocument()
    expect(screen.getByText('PAIR-MANNY')).toBeInTheDocument()
  })

  it('requires an explicit confirmation action', () => {
    const run = vi.fn().mockResolvedValue(undefined)
    render(<DevicePanel view="home" snapshot={snapshot('CONFIRMING')} mcpConnected busy={false} run={run} {...financeProps} />)

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    expect(run).toHaveBeenCalledOnce()
  })

  it('exposes camera and microphone privacy controls', () => {
    render(<DevicePanel view="settings" snapshot={snapshot('IDLE')} mcpConnected busy={false} run={vi.fn()} {...financeProps} />)

    expect(screen.getByRole('button', { name: 'Mute microphone' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Disable camera' })).toBeInTheDocument()
  })
})
