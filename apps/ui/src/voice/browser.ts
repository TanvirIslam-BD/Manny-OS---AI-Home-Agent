interface SpeechResultEvent extends Event {
  results: { [index: number]: { [index: number]: { transcript: string } } }
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start(): void
  stop(): void
  onresult: ((event: SpeechResultEvent) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

function recognitionConstructor(): SpeechRecognitionConstructor | undefined {
  const browser = window as unknown as {
    SpeechRecognition?: SpeechRecognitionConstructor
    webkitSpeechRecognition?: SpeechRecognitionConstructor
  }
  return browser.SpeechRecognition ?? browser.webkitSpeechRecognition
}

export function supportsBrowserVoice(): boolean {
  return recognitionConstructor() !== undefined && 'speechSynthesis' in window
}

export function listenOnce(language = 'auto'): Promise<string> {
  const Recognition = recognitionConstructor()
  if (!Recognition) return Promise.reject(new Error('Speech recognition is unavailable'))
  return new Promise((resolve, reject) => {
    const recognition = new Recognition()
    let settled = false
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = language === 'auto' ? navigator.language : language
    recognition.onresult = (event) => {
      settled = true
      resolve(event.results[0][0].transcript)
      recognition.stop()
    }
    recognition.onerror = () => {
      settled = true
      reject(new Error('Microphone recognition failed'))
    }
    recognition.onend = () => {
      if (!settled) reject(new Error('No speech was detected'))
    }
    recognition.start()
  })
}

/**
 * Whether the reply was actually spoken, and why not when it was not.
 *
 * Silence used to be indistinguishable from success. Browser speech depends on voices
 * the operating system provides, and a Bengali or Hindi voice is absent from a default
 * Windows install — so a reply in those languages produced no sound, no error, and no
 * explanation. Reporting the reason is the same rule the rest of Manny follows: a
 * missing dependency says so rather than looking like it worked.
 */
export type SpeechOutcome = { spoken: true } | { spoken: false; reason: string }

/**
 * getVoices() is empty until the browser has loaded them, and fires `voiceschanged`
 * when it has — except where it never fires at all, hence the timeout.
 */
async function loadVoices(): Promise<SpeechSynthesisVoice[]> {
  const available = window.speechSynthesis.getVoices()
  if (available.length > 0) return available
  return new Promise((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      resolve(window.speechSynthesis.getVoices())
    }
    window.speechSynthesis.addEventListener('voiceschanged', finish, { once: true })
    window.setTimeout(finish, 1000)
  })
}

function voiceFor(voices: SpeechSynthesisVoice[], language: string): SpeechSynthesisVoice | undefined {
  const wanted = language.toLowerCase()
  const base = wanted.split('-')[0]
  return (
    voices.find((candidate) => candidate.lang.toLowerCase() === wanted)
    ?? voices.find((candidate) => candidate.lang.toLowerCase().split('-')[0] === base)
  )
}

/**
 * `untilFinished` resolves when the audio stops rather than when it starts.
 *
 * The default stays resolve-on-start because `announce` awaits it before releasing
 * the form, and blocking a button for the length of a spoken reply would make the UI
 * feel slower than it is. Sequencing a streamed reply needs the opposite: each
 * sentence has to finish before the next begins, or they play over each other.
 */
export interface SpeechTiming {
  untilFinished?: boolean
}

export async function speak(
  text: string,
  language = 'en',
  { untilFinished = false }: SpeechTiming = {},
): Promise<SpeechOutcome> {
  if (!('speechSynthesis' in window)) {
    return { spoken: false, reason: 'This browser cannot speak.' }
  }
  if (!text.trim()) return { spoken: false, reason: 'There was nothing to say.' }

  // Only clear the queue when this call owns the whole reply. A streamed reply
  // enqueues sentence after sentence, and cancelling here would cut off the one
  // still being spoken every time the next arrived.
  if (!untilFinished) window.speechSynthesis.cancel()
  const voices = await loadVoices()
  const voice = voiceFor(voices, language)
  if (!voice) {
    // Deliberately silent rather than reading the text with a voice for another
    // language: an English voice pronouncing Bengali script produces noise, not speech.
    // The reason states the fact and stops there — the caller can fall back to the
    // device's own synthesiser, and only it knows whether that worked.
    return {
      spoken: false,
      reason: `No ${language} voice is installed in this browser.`,
    }
  }

  const utterance = new SpeechSynthesisUtterance(text)
  utterance.lang = language
  utterance.voice = voice
  utterance.rate = 1
  if (!untilFinished) {
    window.speechSynthesis.speak(utterance)
    return { spoken: true }
  }
  await new Promise<void>((resolve) => {
    // Resolve on error as well: a sentence that failed to speak must not strand the
    // rest of the reply behind it.
    utterance.onend = () => resolve()
    utterance.onerror = () => resolve()
    window.speechSynthesis.speak(utterance)
  })
  return { spoken: true }
}

/**
 * The clip currently playing, so it can be stopped.
 *
 * `speechSynthesis.cancel()` silences browser voices globally, but device-synthesised
 * audio plays through an element nobody else holds a reference to. Without this a
 * cancelled turn keeps talking over the next one.
 */
let playing: HTMLAudioElement | null = null

/**
 * Play audio the device synthesised, for languages this browser has no voice for.
 *
 * Resolves once playback starts by default, matching `speak`. Pass `untilFinished`
 * to wait for the end, which sequencing a streamed reply requires. The object URL is
 * released on ending or failing so a long session does not accumulate blobs.
 */
export async function playAudio(
  audio: Blob,
  { untilFinished = false }: SpeechTiming = {},
): Promise<void> {
  const url = URL.createObjectURL(audio)
  const element = new Audio(url)
  playing = element
  const release = () => {
    URL.revokeObjectURL(url)
    if (playing === element) playing = null
  }
  const finished = new Promise<void>((resolve) => {
    // Errors resolve rather than reject: one unplayable sentence should not strand
    // the remainder of the reply behind it.
    element.addEventListener('ended', () => resolve(), { once: true })
    element.addEventListener('error', () => resolve(), { once: true })
  })
  element.addEventListener('ended', release, { once: true })
  element.addEventListener('error', release, { once: true })
  try {
    await element.play()
  } catch (reason) {
    release()
    throw reason
  }
  if (untilFinished) await finished
}

/** Silence everything at once: queued browser utterances and device audio alike. */
export function stopSpeaking(): void {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  if (playing) {
    playing.pause()
    playing = null
  }
}
