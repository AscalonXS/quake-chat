import { useEffect, useMemo, useRef } from 'react'
import Globe, { type GlobeMethods } from 'react-globe.gl'
import type { Quake } from './types'

// Землетрясение, у которого точно есть координаты.
type QuakePoint = Quake & { lat: number; lon: number }

type Props = {
  quakes: Quake[]
  selectedId: string | null
  onSelect: (quake: Quake) => void
  size: number // ширина и высота глобуса в пикселях
}

function pointColor(mag: number) {
  if (mag >= 5) return '#dc2626' // красный
  if (mag >= 4) return '#f59e0b' // оранжевый
  if (mag >= 2.5) return '#fde047' // жёлтый
  return '#e2e8f0' // светло-серый: слабые, никем не ощущаются
}

// Чем сильнее землетрясение, тем больше точка.
function pointRadius(mag: number) {
  return 0.25 + Math.max(0, mag) * 0.22
}

export default function QuakeGlobe({ quakes, selectedId, onSelect, size }: Props) {
  const globeRef = useRef<GlobeMethods | undefined>(undefined)

  // На глобус попадают только события с координатами.
  // Слабые рисуем первыми, чтобы сильные оказались сверху.
  const points = useMemo(
    () =>
      quakes
        .filter((q): q is QuakePoint => q.lat !== undefined && q.lon !== undefined)
        .sort((a, b) => a.mag - b.mag),
    [quakes],
  )

  // Медленное вращение. Останавливается, когда пользователь трогает глобус.
  useEffect(() => {
    const controls = globeRef.current?.controls()
    if (!controls) return
    controls.autoRotate = true
    controls.autoRotateSpeed = 0.5
    controls.enableZoom = false // колесо мыши должно прокручивать страницу, а не глобус
    const stop = () => {
      controls.autoRotate = false
    }
    controls.addEventListener('start', stop)
    return () => controls.removeEventListener('start', stop)
  }, [])

  // Выбрали землетрясение в списке или на глобусе — поворачиваем глобус к нему.
  useEffect(() => {
    const selected = points.find((q) => q.id === selectedId)
    const globe = globeRef.current
    if (!selected || !globe) return
    globe.controls().autoRotate = false
    globe.pointOfView({ lat: selected.lat, lng: selected.lon, altitude: 2.3 }, 800)
  }, [selectedId, points])

  return (
    <Globe
      ref={globeRef}
      width={size}
      height={size}
      animateIn={false}
      backgroundColor="rgba(0,0,0,0)"
      globeImageUrl="/earth.jpg"
      atmosphereColor="#93c5fd"
      atmosphereAltitude={0.15}
      pointsData={points}
      pointLat="lat"
      pointLng="lon"
      pointAltitude={0.01}
      pointRadius={(q) => pointRadius((q as QuakePoint).mag) * ((q as QuakePoint).id === selectedId ? 1.6 : 1)}
      pointColor={(q) => ((q as QuakePoint).id === selectedId ? '#ffffff' : pointColor((q as QuakePoint).mag))}
      pointLabel={(q) => `M ${(q as QuakePoint).mag.toFixed(1)} · ${(q as QuakePoint).place}`}
      pointsMerge={false}
      onPointClick={(q) => onSelect(q as QuakePoint)}
    />
  )
}
