import { useState, type FormEvent } from 'react'
import { completeReminder, createReminder } from '../api/client'
import type { Reminder } from '../types'

function whenLabel(due: string): string {
  const date = new Date(due)
  const now = new Date()
  const minutes = Math.round((date.getTime() - now.getTime()) / 60000)
  if (minutes < -1) return 'Overdue'
  if (minutes < 60) return `in ${Math.max(0, minutes)} min`
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function AlertsView({
  reminders,
  busy,
  onChanged,
}: {
  reminders: Reminder[]
  busy: boolean
  onChanged: () => Promise<void>
}) {
  const [title, setTitle] = useState('')
  const [minutes, setMinutes] = useState('60')
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim()) return
    setWorking(true)
    setMessage(null)
    try {
      const due = new Date(Date.now() + Number(minutes) * 60_000)
      await createReminder(title.trim(), due.toISOString())
      setTitle('')
      await onChanged()
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Could not save that reminder')
    } finally {
      setWorking(false)
    }
  }

  async function complete(id: string) {
    setWorking(true)
    try {
      await completeReminder(id)
      await onChanged()
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Could not complete that reminder')
    } finally {
      setWorking(false)
    }
  }

  return (
    <section className="alerts" aria-label="Alerts and reminders">
      <header>
        <span className="eyebrow">Reminders</span>
        <small>{reminders.length === 0 ? 'Nothing scheduled' : `${reminders.length} upcoming`}</small>
      </header>
      {reminders.length > 0 && (
        <ul className="alerts__list">
          {reminders.slice(0, 4).map((item) => (
            <li key={item.id}>
              <div>
                <strong>{item.title}</strong>
                <small>{whenLabel(item.due_at)}</small>
              </div>
              <button
                aria-label={`Complete ${item.title}`}
                disabled={busy || working}
                type="button"
                onClick={() => void complete(item.id)}
              >
                ✓
              </button>
            </li>
          ))}
        </ul>
      )}
      <form className="alerts__add" onSubmit={(event) => void add(event)}>
        <input
          aria-label="Reminder"
          maxLength={160}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Remind me to…"
          value={title}
        />
        <select aria-label="When" value={minutes} onChange={(event) => setMinutes(event.target.value)}>
          <option value="15">15 min</option>
          <option value="60">1 hour</option>
          <option value="240">4 hours</option>
          <option value="1440">Tomorrow</option>
        </select>
        <button disabled={busy || working || !title.trim()} type="submit">Add</button>
      </form>
      {message && <small className="alerts__message">{message}</small>}
    </section>
  )
}
