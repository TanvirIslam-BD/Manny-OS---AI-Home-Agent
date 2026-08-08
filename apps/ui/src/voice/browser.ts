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

export function listenOnce(): Promise<string> {
  const Recognition = recognitionConstructor()
  if (!Recognition) return Promise.reject(new Error('Speech recognition is unavailable'))
  return new Promise((resolve, reject) => {
    const recognition = new Recognition()
    let settled = false
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = 'en-US'
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

export function speak(text: string): void {
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(text)
  utterance.rate = 1
  window.speechSynthesis.speak(utterance)
}
