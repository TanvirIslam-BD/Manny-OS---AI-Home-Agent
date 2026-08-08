import { useEffect, useRef, useState } from 'react'

interface FaceDetectorLike {
  detect(source: HTMLVideoElement): Promise<unknown[]>
}

type FaceDetectorConstructor = new (options?: { maxDetectedFaces?: number }) => FaceDetectorLike

// Motion differencing runs on a thumbnail: enough signal to tell a still room
// from an occupied one, cheap enough to run beside everything else.
const SAMPLE_WIDTH = 64
const SAMPLE_HEIGHT = 48
const MOTION_THRESHOLD = 9
const STILLNESS_GRACE_MS = 20_000
const INTERVAL_MS = 1_500

function faceDetector(): FaceDetectorConstructor | undefined {
  return (window as unknown as { FaceDetector?: FaceDetectorConstructor }).FaceDetector
}

export default function CameraPresence({
  onPeopleCount,
}: {
  onPeopleCount: (count: number) => Promise<void>
}) {
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const previous = useRef<Uint8ClampedArray | null>(null)
  const lastMotion = useRef<number>(0)
  const reported = useRef<number>(0)
  const [active, setActive] = useState(false)
  const [detail, setDetail] = useState('Camera is off')

  useEffect(() => () => {
    stream.current?.getTracks().forEach((track) => track.stop())
  }, [])

  useEffect(() => {
    if (!active) return
    const Detector = faceDetector()
    const detector = Detector ? new Detector({ maxDetectedFaces: 4 }) : null
    const canvas = document.createElement('canvas')
    canvas.width = SAMPLE_WIDTH
    canvas.height = SAMPLE_HEIGHT
    const context = canvas.getContext('2d', { willReadFrequently: true })

    const report = async (count: number, message: string) => {
      setDetail(message)
      if (count !== reported.current) {
        reported.current = count
        await onPeopleCount(count)
      }
    }

    const sampleMotion = (): number | null => {
      if (!context || !video.current || video.current.readyState < 2) return null
      context.drawImage(video.current, 0, 0, SAMPLE_WIDTH, SAMPLE_HEIGHT)
      const frame = context.getImageData(0, 0, SAMPLE_WIDTH, SAMPLE_HEIGHT).data
      const earlier = previous.current
      previous.current = new Uint8ClampedArray(frame)
      if (!earlier) return null
      let total = 0
      // Luminance only, every fourth pixel: colour and full resolution buy
      // nothing here and cost battery.
      for (let index = 0; index < frame.length; index += 16) {
        total += Math.abs(frame[index] - earlier[index])
      }
      return total / (frame.length / 16)
    }

    const timer = window.setInterval(() => {
      if (detector && video.current) {
        detector.detect(video.current)
          .then((faces) => report(
            faces.length,
            `${faces.length} ${faces.length === 1 ? 'person' : 'people'} detected locally`,
          ))
          .catch(() => setDetail('Local detection paused'))
        return
      }
      const difference = sampleMotion()
      if (difference === null) return
      const now = Date.now()
      if (difference >= MOTION_THRESHOLD) lastMotion.current = now
      const occupied = now - lastMotion.current < STILLNESS_GRACE_MS
      void report(
        occupied ? 1 : 0,
        occupied
          ? 'Someone is nearby · motion only, this browser cannot count people'
          : 'No movement seen · motion only, this browser cannot count people',
      )
    }, INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [active, onPeopleCount])

  async function start() {
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      if (video.current) video.current.srcObject = stream.current
      previous.current = null
      lastMotion.current = Date.now()
      setActive(true)
      setDetail(
        faceDetector()
          ? 'Camera preview active · frames stay in this browser'
          : 'Watching for movement · frames stay in this browser',
      )
    } catch {
      setDetail('Camera permission was not granted')
    }
  }

  function stop() {
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
    if (video.current) video.current.srcObject = null
    previous.current = null
    reported.current = 0
    setActive(false)
    setDetail('Camera is off')
    void onPeopleCount(0)
  }

  return (
    <div className="camera-presence">
      <video ref={video} autoPlay muted playsInline aria-label="Private local camera preview" />
      <div><strong>Desktop camera</strong><p>{detail}</p></div>
      <button type="button" onClick={() => void (active ? stop() : start())}>{active ? 'Stop' : 'Start'}</button>
    </div>
  )
}
