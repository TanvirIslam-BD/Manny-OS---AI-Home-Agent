import { playAudio, speak, stopSpeaking } from './browser'

/**
 * Speaks a reply sentence by sentence, in order, as the model writes it.
 *
 * The device has always done this — the voice coordinator synthesises each piece and
 * plays it before the next — but the simulator waited for the whole reply and then
 * said it in one go. On a CPU-only machine that is several seconds of silence while
 * the text is already on screen.
 *
 * Order is the whole problem. Sentences arrive faster than they can be spoken, and
 * both playback paths are asynchronous, so anything that fires them as they arrive
 * plays them on top of each other. Each sentence is therefore chained behind the one
 * before it, and every step waits for audio to stop rather than to start.
 */
export interface SpeechQueue {
  /** Queue one sentence. Returns immediately; playback happens in order. */
  say(text: string, language: string): void
  /** Drop anything queued and silence what is playing. */
  cancel(): void
  /** Whether anything has actually been spoken since the last cancel. */
  spokeAnything(): boolean
  /** Why the last sentence could not be spoken, if it could not be. */
  failure(): string | null
}

export function createSpeechQueue(
  synthesize: (text: string, language: string) => Promise<Blob>,
): SpeechQueue {
  let tail: Promise<void> = Promise.resolve()
  // Bumped on cancel so work already queued behind the current sentence becomes a
  // no-op instead of speaking over whatever replaced it.
  let generation = 0
  let spoke = false
  let failed: string | null = null

  async function speakOne(text: string, language: string, era: number): Promise<void> {
    if (era !== generation || !text.trim()) return
    const outcome = await speak(text, language, { untilFinished: true })
    if (outcome.spoken) {
      spoke = true
      return
    }
    if (era !== generation) return
    try {
      await playAudio(await synthesize(text, language), { untilFinished: true })
      spoke = true
    } catch (reason) {
      // Recorded rather than thrown. The caller reports it once at the end of the
      // reply; raising here would break the chain and silence every later sentence.
      failed = `${outcome.reason} ${reason instanceof Error ? reason.message : 'Speech failed.'}`
    }
  }

  return {
    say(text, language) {
      const era = generation
      tail = tail.then(() => speakOne(text, language, era)).catch(() => undefined)
    },
    cancel() {
      generation += 1
      spoke = false
      failed = null
      tail = Promise.resolve()
      stopSpeaking()
    },
    spokeAnything: () => spoke,
    failure: () => failed,
  }
}
