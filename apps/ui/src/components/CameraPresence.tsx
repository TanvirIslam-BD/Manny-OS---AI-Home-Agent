import { useEffect, useRef, useState } from 'react'

interface FaceDetectorLike {
  detect(source: HTMLVideoElement): Promise<unknown[]>
}

type FaceDetectorConstructor = new (options?: { maxDetectedFaces?: number }) => FaceDetectorLike

export default function CameraPresence({
  onPeopleCount,
}: {
  onPeopleCount: (count: number) => Promise<void>
}) {
  const video = useRef<HTMLVideoElement>(null)
  const stream = useRef<MediaStream | null>(null)
  const [active, setActive] = useState(false)
  const [detail, setDetail] = useState('Camera is off')

  useEffect(() => () => {
    stream.current?.getTracks().forEach((track) => track.stop())
  }, [])

  useEffect(() => {
    if (!active) return
    const Detector = (window as unknown as { FaceDetector?: FaceDetectorConstructor }).FaceDetector
    if (!Detector) return
    const detector = new Detector({ maxDetectedFaces: 4 })
    const timer = window.setInterval(() => {
      if (!video.current) return
      detector.detect(video.current).then((faces) => {
        setDetail(`${faces.length} ${faces.length === 1 ? 'person' : 'people'} detected locally`)
        return onPeopleCount(faces.length)
      }).catch(() => setDetail('Local detection paused'))
    }, 1500)
    return () => window.clearInterval(timer)
  }, [active, onPeopleCount])

  async function start() {
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
      if (video.current) video.current.srcObject = stream.current
      setActive(true)
      const Detector = (window as unknown as { FaceDetector?: FaceDetectorConstructor }).FaceDetector
      setDetail(Detector ? 'Camera preview active · frames stay in this browser' : 'Preview active · automatic detection unavailable in this browser')
    } catch {
      setDetail('Camera permission was not granted')
    }
  }

  function stop() {
    stream.current?.getTracks().forEach((track) => track.stop())
    stream.current = null
    if (video.current) video.current.srcObject = null
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
