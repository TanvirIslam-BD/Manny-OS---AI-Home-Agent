import { afterEach, describe, expect, it, vi } from 'vitest'

import { speak } from './browser'

type Voice = { lang: string; name: string }

function withSynthesis(voices: Voice[]) {
  const spoken: { text: string; lang: string; voice: unknown }[] = []
  const synthesis = {
    cancel: vi.fn(),
    getVoices: () => voices,
    addEventListener: vi.fn(),
    speak: (utterance: { text: string; lang: string; voice: unknown }) => spoken.push(utterance),
  }
  vi.stubGlobal('speechSynthesis', synthesis)
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    text: string
    lang = ''
    voice: unknown = null
    rate = 1
    constructor(text: string) { this.text = text }
  })
  return { spoken, synthesis }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('speak', () => {
  it('speaks when the system has a voice for the language', async () => {
    const { spoken } = withSynthesis([{ lang: 'en-US', name: 'English' }])

    const outcome = await speak('Hello there.', 'en-US')

    expect(outcome).toEqual({ spoken: true })
    expect(spoken).toHaveLength(1)
    expect(spoken[0].text).toBe('Hello there.')
  })

  it('matches on the base language when the exact locale is missing', async () => {
    const { spoken } = withSynthesis([{ lang: 'bn-IN', name: 'Bengali India' }])

    const outcome = await speak('আপনি ভালো আছেন।', 'bn-BD')

    expect(outcome).toEqual({ spoken: true })
    expect(spoken).toHaveLength(1)
  })

  it('reports why it stayed silent when no voice exists for the language', async () => {
    // The bug this covers: a default Windows install ships no Bengali voice, so a
    // Bengali reply produced no sound, no error and no explanation. Silence was
    // indistinguishable from success.
    const { spoken } = withSynthesis([{ lang: 'en-US', name: 'English' }])

    const outcome = await speak('আপনি ভালো আছেন।', 'bn-BD')

    expect(outcome.spoken).toBe(false)
    expect(outcome.spoken === false && outcome.reason).toContain('bn-BD')
    // Deliberately not spoken: an English voice reading Bengali script is noise.
    expect(spoken).toHaveLength(0)
  })

  it('does not try to speak an empty reply', async () => {
    const { spoken } = withSynthesis([{ lang: 'en-US', name: 'English' }])

    const outcome = await speak('   ', 'en-US')

    expect(outcome.spoken).toBe(false)
    expect(spoken).toHaveLength(0)
  })

  it('reports a browser that cannot speak at all', async () => {
    vi.unstubAllGlobals()
    const original = Object.getOwnPropertyDescriptor(window, 'speechSynthesis')
    // @ts-expect-error deliberately removing the API to model an unsupported browser
    delete window.speechSynthesis

    const outcome = await speak('Hello.', 'en-US')

    expect(outcome.spoken).toBe(false)
    if (original) Object.defineProperty(window, 'speechSynthesis', original)
  })
})
