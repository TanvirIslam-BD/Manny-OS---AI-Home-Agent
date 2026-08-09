import { fireEvent, render, screen } from '@testing-library/react'
import { useRef, useState } from 'react'
import { describe, expect, it } from 'vitest'

import OnScreenKeyboard, { type KeyboardLayout } from './OnScreenKeyboard'

/**
 * A controlled input, because that is what every real call site uses. If the
 * keyboard bypassed React's onChange the value would snap back on the next render,
 * and a test against an uncontrolled input would not notice.
 */
function Harness({
  layout = 'latin',
  maxLength,
  sanitise,
}: {
  layout?: KeyboardLayout
  maxLength?: number
  sanitise?: (value: string) => string
}) {
  const ref = useRef<HTMLInputElement | null>(null)
  const [value, setValue] = useState('')
  return (
    <>
      <input
        aria-label="Field"
        maxLength={maxLength}
        onChange={(event) => setValue(sanitise ? sanitise(event.target.value) : event.target.value)}
        ref={ref}
        value={value}
      />
      <OnScreenKeyboard layout={layout} target={ref} />
    </>
  )
}

function field(): HTMLInputElement {
  return screen.getByLabelText('Field') as HTMLInputElement
}

function press(name: string): void {
  // pointerdown, not click: that is the event the keys act on so the field never
  // loses focus.
  fireEvent.pointerDown(screen.getByRole('button', { name }))
}

describe('OnScreenKeyboard', () => {
  it('types through the controlled input so the value survives a render', () => {
    render(<Harness />)

    press('h')
    press('i')

    expect(field().value).toBe('hi')
  })

  it('keeps focus on the field so the caret is not lost', () => {
    render(<Harness />)
    field().focus()

    const event = fireEvent.pointerDown(screen.getByRole('button', { name: 'a' }))

    // A default-prevented pointerdown is what stops the button taking focus.
    expect(event).toBe(false)
    expect(document.activeElement).toBe(field())
  })

  it('inserts at the caret rather than only at the end', () => {
    render(<Harness />)
    press('a')
    press('c')
    field().setSelectionRange(1, 1)

    press('b')

    expect(field().value).toBe('abc')
    expect(field().selectionStart).toBe(2)
  })

  it('shifts one key and then releases, like a phone keyboard', () => {
    render(<Harness />)

    press('Shift')
    // The keys relabel themselves while shifted, which is the visible cue that it
    // is on.
    expect(screen.queryByRole('button', { name: 'a' })).not.toBeInTheDocument()
    press('A')
    press('b')

    expect(field().value).toBe('Ab')
  })

  it('reaches digits and punctuation through the symbols layer', () => {
    render(<Harness />)

    press('?123')
    press('4')
    press('@')

    expect(field().value).toBe('4@')
  })

  it('deletes backwards and removes a selection whole', () => {
    render(<Harness />)
    press('a')
    press('b')
    press('c')

    press('Backspace')
    expect(field().value).toBe('ab')

    field().setSelectionRange(0, 2)
    press('Backspace')
    expect(field().value).toBe('')
  })

  it('refuses a key that would exceed the field maximum', () => {
    render(<Harness maxLength={2} />)

    press('a')
    press('b')
    press('c')

    expect(field().value).toBe('ab')
  })

  it('respects the validation the field already applies', () => {
    // The passcode strips non-digits in its own onChange. Typing through the native
    // event path means the keyboard inherits that instead of bypassing it.
    render(<Harness sanitise={(value) => value.replace(/\D/g, '')} />)

    press('?123')
    press('7')
    press('abc')
    press('q')

    expect(field().value).toBe('7')
  })

  it('offers a numeric keypad with no letters for the passcode', () => {
    render(<Harness layout="numeric" />)

    expect(screen.queryByRole('button', { name: 'q' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Shift' })).not.toBeInTheDocument()

    press('1')
    press('2')
    press('3')
    press('4')
    expect(field().value).toBe('1234')

    press('Clear')
    expect(field().value).toBe('')
  })

  it('does nothing when no field is attached', () => {
    function Detached() {
      const ref = useRef<HTMLInputElement | null>(null)
      return <OnScreenKeyboard target={ref} />
    }
    render(<Detached />)

    expect(() => press('a')).not.toThrow()
  })
})
