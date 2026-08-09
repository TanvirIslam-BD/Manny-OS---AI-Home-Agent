import { afterEach, describe, expect, it, vi } from 'vitest'

import { createSpeechQueue } from './queue'

type Voice = { lang: string; name: string }

/**
 * Utterances finish asynchronously, as they do in a browser. If the queue fired the
 * next sentence without waiting, `speaking` would hold more than one entry at a time
 * — which is precisely the overlap these tests exist to catch.
 */
function withSynthesis(voices: Voice[], speechMs = 5) {
  const finished: string[] = []
  const speaking: string[] = []
  let overlapped = false

  vi.stubGlobal('speechSynthesis', {
    cancel: vi.fn(),
    getVoices: () => voices,
    addEventListener: vi.fn(),
    speak: (utterance: { text: string; onend?: () => void }) => {
      speaking.push(utterance.text)
      if (speaking.length > 1) overlapped = true
      setTimeout(() => {
        speaking.splice(speaking.indexOf(utterance.text), 1)
        finished.push(utterance.text)
        utterance.onend?.()
      }, speechMs)
    },
  })
  vi.stubGlobal('SpeechSynthesisUtterance', class {
    text: string
    lang = ''
    voice: unknown = null
    rate = 1
    onend: (() => void) | null = null
    onerror: (() => void) | null = null
    constructor(text: string) { this.text = text }
  })
  return { finished, didOverlap: () => overlapped }
}

const neverCalled = () => Promise.reject(new Error('the device should not have been asked'))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('createSpeechQueue', () => {
  it('speaks sentences in order and never over each other', async () => {
    const { finished, didOverlap } = withSynthesis([{ lang: 'en-US', name: 'English' }])
    const queue = createSpeechQueue(neverCalled)

    queue.say('One.', 'en-US')
    queue.say('Two.', 'en-US')
    queue.say('Three.', 'en-US')
    await vi.waitFor(() => expect(finished).toHaveLength(3))

    // Order is the whole point: sentences arrive faster than they can be spoken.
    expect(finished).toEqual(['One.', 'Two.', 'Three.'])
    expect(didOverlap()).toBe(false)
    expect(queue.spokeAnything()).toBe(true)
  })

  it('falls back to device audio for a language the browser has no voice for', async () => {
    withSynthesis([{ lang: 'en-US', name: 'English' }])
    const asked: string[] = []
    const play = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: () => 'blob:x', revokeObjectURL: vi.fn() })
    vi.stubGlobal('Audio', class {
      constructor(public src: string) {}
      addEventListener(name: string, handler: () => void) {
        if (name === 'ended') setTimeout(handler, 1)
      }
      play = play
    })
    const queue = createSpeechQueue(async (text) => {
      asked.push(text)
      return new Blob([new Uint8Array([1])])
    })

    queue.say('আপনার বাজেট ভালো আছে।', 'bn-BD')
    await vi.waitFor(() => expect(queue.spokeAnything()).toBe(true))

    expect(asked).toEqual(['আপনার বাজেট ভালো আছে।'])
    expect(play).toHaveBeenCalled()
  })

  it('records a failure without stranding the rest of the reply', async () => {
    withSynthesis([{ lang: 'en-US', name: 'English' }])
    const queue = createSpeechQueue(() => Promise.reject(new Error('Synthesis is unavailable.')))

    queue.say('আপনার বাজেট।', 'bn-BD')
    queue.say('Second sentence in English.', 'en-US')
    await vi.waitFor(() => expect(queue.spokeAnything()).toBe(true))

    // The English sentence still spoke even though the Bengali one could not.
    expect(queue.failure()).toContain('Synthesis is unavailable.')
  })

  it('cancelling silences what is queued behind the current sentence', async () => {
    const { finished } = withSynthesis([{ lang: 'en-US', name: 'English' }], 20)
    const queue = createSpeechQueue(neverCalled)

    queue.say('One.', 'en-US')
    queue.say('Two.', 'en-US')
    queue.cancel()
    await new Promise((resolve) => setTimeout(resolve, 60))

    // Whatever had already started may finish; nothing queued behind it should run,
    // or a cancelled turn talks over the one that replaced it.
    expect(finished).not.toContain('Two.')
    expect(queue.spokeAnything()).toBe(false)
    expect(queue.failure()).toBeNull()
  })
})
