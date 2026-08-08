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
    listening_enabled: false,
    listening_available: false,
    language: 'auto',
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

  it('disables the listening control when the device has no microphone loop', () => {
    render(<DevicePanel view="settings" snapshot={snapshot('IDLE')} mcpConnected busy={false} run={vi.fn()} {...financeProps} />)

    expect(screen.getByRole('button', { name: 'Start always listening' })).toBeDisabled()
    expect(screen.getByText('Unavailable on this device')).toBeInTheDocument()
  })

  it('toggles always-on listening when the loop is available', () => {
    const run = vi.fn().mockResolvedValue(undefined)
    const listening = { ...snapshot('IDLE'), listening_available: true, listening_enabled: true }
    render(<DevicePanel view="settings" snapshot={listening} mcpConnected busy={false} run={run} {...financeProps} />)

    fireEvent.click(screen.getByRole('button', { name: 'Stop always listening' }))
    expect(run).toHaveBeenCalledOnce()
  })

  it('shows the configured capture window and presence detector', () => {
    const settings = {
      environment: 'raspberrypi',
      deviceId: 'manny-pi5',
      hardwareMode: 'real',
      cameraEnabled: true,
      voice: { defaultLanguage: 'auto', loopEnabled: true, loopAvailable: true, captureSeconds: 3, vadThreshold: 0.02 },
      presence: { detector: 'opencv_hog', available: true },
    }
    render(<DevicePanel view="settings" snapshot={snapshot('IDLE')} mcpConnected busy={false} run={vi.fn()} settings={settings} {...financeProps} />)

    expect(screen.getByText('3s · speech threshold 0.02')).toBeInTheDocument()
    expect(screen.getByText('opencv_hog')).toBeInTheDocument()
  })
})

describe('DevicePanel language selector', () => {
  it('offers automatic detection alongside the supported languages', () => {
    render(<DevicePanel view="settings" snapshot={snapshot('IDLE')} mcpConnected busy={false} run={vi.fn()} {...financeProps} />)

    const selector = screen.getByRole('combobox', { name: 'Language' })
    expect(selector).toHaveValue('auto')
    expect(screen.getByRole('option', { name: 'Auto detect' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'বাংলা' })).toBeInTheDocument()
  })

  it('applies the chosen language to the device', () => {
    const run = vi.fn().mockResolvedValue(undefined)
    render(<DevicePanel view="settings" snapshot={snapshot('IDLE')} mcpConnected busy={false} run={run} {...financeProps} />)

    fireEvent.change(screen.getByRole('combobox', { name: 'Language' }), { target: { value: 'bn-BD' } })
    expect(run).toHaveBeenCalledOnce()
  })

  it('reflects the language already active on the device', () => {
    const bangla = { ...snapshot('IDLE'), language: 'bn-BD' }
    render(<DevicePanel view="settings" snapshot={bangla} mcpConnected busy={false} run={vi.fn()} {...financeProps} />)

    expect(screen.getByRole('combobox', { name: 'Language' })).toHaveValue('bn-BD')
  })
})
