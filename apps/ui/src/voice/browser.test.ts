import { afterEach, describe, expect, it, vi } from 'vitest'

import { playAudio, speak } from './browser'

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

  it('states only what it knows, leaving the caller free to try the device', async () => {
    // The reason used to end "so the reply is shown but not spoken", which is now
    // premature: the device's own synthesiser is asked next and usually speaks it.
    const { spoken } = withSynthesis([{ lang: 'en-US', name: 'English' }])

    const outcome = await speak('আপনি ভালো আছেন।', 'bn-BD')

    expect(outcome.spoken === false && outcome.reason).not.toContain('not spoken')
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

describe('playAudio', () => {
  function withAudio(play: () => Promise<void>) {
    const revoked: string[] = []
    vi.stubGlobal('URL', {
      createObjectURL: () => 'blob:manny-speech',
      revokeObjectURL: (url: string) => revoked.push(url),
    })
    const listeners = new Map<string, () => void>()
    vi.stubGlobal('Audio', class {
      constructor(public src: string) {}
      addEventListener(name: string, handler: () => void) { listeners.set(name, handler) }
      play = play
    })
    return { revoked, listeners }
  }

  it('plays speech the device synthesised for a language the browser lacks', async () => {
    const { revoked, listeners } = withAudio(() => Promise.resolve())

    await playAudio(new Blob([new Uint8Array([1, 2])], { type: 'audio/wav' }))

    expect(revoked).toHaveLength(0)
    // Released on ending rather than on start, so a long session does not
    // accumulate blob URLs for every reply Manny speaks.
    listeners.get('ended')?.()
    expect(revoked).toEqual(['blob:manny-speech'])
  })

  it('releases the blob and rethrows when playback is refused', async () => {
    const { revoked } = withAudio(() => Promise.reject(new Error('autoplay blocked')))

    await expect(playAudio(new Blob([new Uint8Array([1])]))).rejects.toThrow('autoplay blocked')
    expect(revoked).toEqual(['blob:manny-speech'])
  })
})
