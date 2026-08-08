import { useState, type FormEvent } from 'react'
import { lockDevice, setPasscode, unlockDevice } from '../api/client'
import type { SecurityStatus } from '../types'

export default function PasscodePanel({
  security,
  busy,
  onChange,
}: {
  security: SecurityStatus
  busy: boolean
  onChange: (status: SecurityStatus) => void
}) {
  const [entry, setEntry] = useState('')
  const [current, setCurrent] = useState('')
  const [changing, setChanging] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [working, setWorking] = useState(false)

  const mode = !security.passcode_set ? 'create' : changing ? 'change' : security.unlocked ? 'unlocked' : 'locked'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setWorking(true)
    setMessage(null)
    try {
      const status =
        mode === 'locked'
          ? await unlockDevice(entry)
          : await setPasscode(entry, mode === 'change' ? current : undefined)
      onChange(status)
      setEntry('')
      setCurrent('')
      setChanging(false)
      setMessage(mode === 'locked' ? 'Unlocked' : 'Passcode saved')
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'That did not work')
    } finally {
      setWorking(false)
    }
  }

  if (mode === 'unlocked') {
    return (
      <div className="passcode" role="group" aria-label="Passcode">
        <div className="passcode__row">
          <span>Passcode</span>
          <small>Unlocked · private views are visible</small>
        </div>
        <div className="passcode__actions">
          <button
            disabled={busy || working}
            type="button"
            onClick={() => void lockDevice().then(onChange)}
          >
            Lock now
          </button>
          <button disabled={busy || working} type="button" onClick={() => setChanging(true)}>
            Change passcode
          </button>
        </div>
        {message && <small className="passcode__message">{message}</small>}
      </div>
    )
  }

  return (
    <form className="passcode" onSubmit={(event) => void submit(event)} aria-label="Passcode">
      <div className="passcode__row">
        <span>Passcode</span>
        <small>
          {mode === 'create'
            ? 'Set one to unlock private financial views'
            : mode === 'change'
              ? 'Enter the current passcode, then the new one'
              : `Locked · ${security.attempts_remaining} attempts left`}
        </small>
      </div>
      {mode === 'change' && (
        <input
          aria-label="Current passcode"
          inputMode="numeric"
          maxLength={12}
          minLength={4}
          onChange={(event) => setCurrent(event.target.value.replace(/\D/g, ''))}
          placeholder="Current"
          required
          type="password"
          value={current}
        />
      )}
      <input
        aria-label={mode === 'locked' ? 'Passcode' : 'New passcode'}
        inputMode="numeric"
        maxLength={12}
        minLength={4}
        onChange={(event) => setEntry(event.target.value.replace(/\D/g, ''))}
        placeholder={mode === 'locked' ? 'Passcode' : '4-12 digits'}
        required
        type="password"
        value={entry}
      />
      <button disabled={busy || working || entry.length < 4} type="submit">
        {mode === 'locked' ? 'Unlock' : 'Save passcode'}
      </button>
      {message && <small className="passcode__message">{message}</small>}
    </form>
  )
}
