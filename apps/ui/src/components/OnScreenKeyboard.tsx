import { useState, type PointerEvent, type RefObject } from 'react'

/**
 * Text entry for a device with a touchscreen and no keyboard.
 *
 * Chromium on Linux has no virtual keyboard, so on the kiosk every text field was
 * unreachable. The passcode was the serious one: with the camera deferred it is the
 * only gate on private financial views, and it could not be typed at all.
 *
 * Two details make this behave like a keyboard rather than a set of buttons.
 *
 * Keys act on pointerdown with the default prevented, so focus never leaves the
 * field. A plain click would blur it first, losing the caret and the selection.
 *
 * Edits go through the input's native value setter and a dispatched `input` event —
 * the same path a real keystroke takes. React's own onChange then runs, so each
 * field keeps its existing validation (the passcode's digits-only filter, for
 * example) and no caller has to thread caret state through its state hook.
 *
 * Latin and numeric layouts only. A Bengali or Chinese layout is not a bigger
 * version of this component — those need conjunct composition and an IME — so on a
 * device whose default recognition language is bn-BD, voice remains the primary
 * input and this is the fallback for Latin text and digits.
 */

export type KeyboardLayout = 'numeric' | 'latin'

const LETTER_ROWS = [
  ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
  ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l'],
  ['z', 'x', 'c', 'v', 'b', 'n', 'm'],
]

const SYMBOL_ROWS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['-', '/', ':', ';', '(', ')', '৳', '&', '@', '"'],
  ['.', ',', '?', '!', "'"],
]

const NUMBER_ROWS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
  ['0'],
]

/**
 * Write to the input the way a keystroke does.
 *
 * Assigning `element.value` directly is invisible to React: it tracks the previous
 * value on the DOM node and would treat the next render as unchanged, so the field
 * would snap back. Going through the prototype's setter and dispatching `input`
 * makes React see a genuine edit.
 */
function typeInto(element: HTMLInputElement, value: string): void {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  if (setter) {
    setter.call(element, value)
  } else {
    element.value = value
  }
  element.dispatchEvent(new Event('input', { bubbles: true }))
}

export default function OnScreenKeyboard({
  target,
  layout = 'latin',
  onDone,
  label = 'On-screen keyboard',
}: {
  target: RefObject<HTMLInputElement | null>
  layout?: KeyboardLayout
  onDone?: () => void
  label?: string
}) {
  const [shifted, setShifted] = useState(false)
  const [symbols, setSymbols] = useState(false)

  function edit(next: (value: string, start: number, end: number) => [string, number]): void {
    const element = target.current
    if (!element) return
    const start = element.selectionStart ?? element.value.length
    const end = element.selectionEnd ?? start
    const [value, caret] = next(element.value, start, end)
    if (element.maxLength > 0 && value.length > element.maxLength) return
    typeInto(element, value)
    // React does not manage the caret, so placing it after the edit sticks.
    element.setSelectionRange(caret, caret)
    element.focus()
  }

  function insert(text: string): void {
    edit((value, start, end) => [value.slice(0, start) + text + value.slice(end), start + text.length])
    if (shifted) setShifted(false)
  }

  function backspace(): void {
    edit((value, start, end) => {
      if (start !== end) return [value.slice(0, start) + value.slice(end), start]
      if (start === 0) return [value, 0]
      return [value.slice(0, start - 1) + value.slice(start), start - 1]
    })
  }

  function clear(): void {
    edit(() => ['', 0])
  }

  // Buttons must not take focus from the field, or the caret is gone by the time
  // the handler runs.
  function hold(action: () => void) {
    return (event: PointerEvent<HTMLButtonElement>) => {
      event.preventDefault()
      action()
    }
  }

  const rows = layout === 'numeric' ? NUMBER_ROWS : symbols ? SYMBOL_ROWS : LETTER_ROWS

  return (
    <div className="osk" role="group" aria-label={label}>
      {rows.map((row, index) => (
        <div className="osk__row" key={index}>
          {row.map((key) => (
            <button
              key={key}
              type="button"
              className="osk__key"
              onPointerDown={hold(() => insert(shifted ? key.toUpperCase() : key))}
            >
              {shifted ? key.toUpperCase() : key}
            </button>
          ))}
        </div>
      ))}
      <div className="osk__row">
        {layout === 'latin' && (
          <>
            <button
              type="button"
              className={`osk__key osk__key--wide${shifted ? ' is-active' : ''}`}
              aria-pressed={shifted}
              onPointerDown={hold(() => setShifted(!shifted))}
            >
              Shift
            </button>
            <button
              type="button"
              className={`osk__key osk__key--wide${symbols ? ' is-active' : ''}`}
              aria-pressed={symbols}
              onPointerDown={hold(() => setSymbols(!symbols))}
            >
              {symbols ? 'abc' : '?123'}
            </button>
            <button
              type="button"
              className="osk__key osk__key--space"
              aria-label="Space"
              onPointerDown={hold(() => insert(' '))}
            >
              space
            </button>
          </>
        )}
        {layout === 'numeric' && (
          <button
            type="button"
            className="osk__key osk__key--wide"
            onPointerDown={hold(clear)}
          >
            Clear
          </button>
        )}
        <button
          type="button"
          className="osk__key osk__key--wide"
          aria-label="Backspace"
          onPointerDown={hold(backspace)}
        >
          ⌫
        </button>
        {onDone && (
          <button
            type="button"
            className="osk__key osk__key--wide"
            onPointerDown={hold(onDone)}
          >
            Done
          </button>
        )}
      </div>
    </div>
  )
}
