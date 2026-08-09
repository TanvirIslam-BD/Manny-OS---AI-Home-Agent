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

export async function speak(text: string, language = 'en'): Promise<SpeechOutcome> {
  if (!('speechSynthesis' in window)) {
    return { spoken: false, reason: 'This browser cannot speak.' }
  }
  if (!text.trim()) return { spoken: false, reason: 'There was nothing to say.' }

  window.speechSynthesis.cancel()
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
  window.speechSynthesis.speak(utterance)
  return { spoken: true }
}

/**
 * Play audio the device synthesised, for languages this browser has no voice for.
 *
 * Resolves once playback starts rather than once it finishes, matching `speak`,
 * which queues an utterance and returns. The object URL is released on either
 * ending or failing so a long session does not accumulate blobs.
 */
export async function playAudio(audio: Blob): Promise<void> {
  const url = URL.createObjectURL(audio)
  const element = new Audio(url)
  const release = () => URL.revokeObjectURL(url)
  element.addEventListener('ended', release, { once: true })
  element.addEventListener('error', release, { once: true })
  try {
    await element.play()
  } catch (reason) {
    release()
    throw reason
  }
}
