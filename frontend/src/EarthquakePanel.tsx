import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { Quake } from './types'
import { useEarthquakes } from './useEarthquakes'

// Глобус тяжёлый (3D-библиотека), поэтому его код загружается отдельно и не задерживает чат.
const QuakeGlobe = lazy(() => import('./QuakeGlobe'))

// В ленте USGS за сутки сотни событий, большинство слабее 2.5 и никем не ощущаются.
// Показываем только заметные и только самые свежие.
const MIN_MAGNITUDE = 2.5
const MAX_ROWS = 10

function timeAgo(timeMs: number, nowMs: number) {
  const minutes = Math.max(0, Math.round((nowMs - timeMs) / 60_000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

function clockTime(timeMs: number) {
  return new Date(timeMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function magnitudeColor(mag: number) {
  if (mag >= 5) return 'bg-red-600 text-white'
  if (mag >= 4) return 'bg-amber-500 text-white'
  return 'bg-line text-ink'
}

type QuakeRowProps = { quake: Quake; now: number; selected: boolean; onSelect: (quake: Quake) => void }

function QuakeRow({ quake, now, selected, onSelect }: QuakeRowProps) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onSelect(quake)}
        aria-pressed={selected}
        className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left ${
          selected ? 'border-accent bg-accent/10' : 'border-line bg-surface hover:border-dim'
        }`}
      >
      <span
        className={`w-12 shrink-0 rounded-md py-1 text-center text-sm font-bold ${magnitudeColor(quake.mag)}`}
      >
        {quake.mag.toFixed(1)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm break-words text-ink">{quake.place}</span>
        <span className="block text-xs text-dim">
          {timeAgo(quake.time, now)} · depth {Math.round(quake.depth_km)} km
        </span>
      </span>
      </button>
    </li>
  )
}

export function EarthquakePanel() {
  const { data, error } = useEarthquakes()
  const [open, setOpen] = useState(false) // на телефоне панель свёрнута, пока не нажмут

  // Текущее время обновляем раз в минуту, чтобы «5 min ago» не застывало.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000)
    return () => clearInterval(timer)
  }, [])

  const notable = data?.events.filter((q) => q.mag >= MIN_MAGNITUDE) ?? []
  const quakes = (notable.length > 0 ? notable : (data?.events ?? [])).slice(0, MAX_ROWS)
  const latest = quakes[0]

  // Выбранное землетрясение: нажали на строку списка или на точку глобуса.
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = data?.events.find((q) => q.id === selectedId) ?? null

  // Глобус рисуется в пикселях, поэтому измеряем ширину места, которое ему отведено.
  const globeBoxRef = useRef<HTMLDivElement>(null)
  const [globeSize, setGlobeSize] = useState(0)
  useEffect(() => {
    const box = globeBoxRef.current
    if (!box) return
    const observer = new ResizeObserver(() => setGlobeSize(Math.min(box.clientWidth, 340)))
    observer.observe(box)
    return () => observer.disconnect()
  }, [])
  const hasCoordinates = data?.events.some((q) => q.lat !== undefined) ?? false

  return (
    <aside className="shrink-0 border-b border-line bg-page lg:flex lg:w-96 lg:flex-col lg:border-b-0 lg:border-l">
      {/* Заголовок. На телефоне это кнопка, которая раскрывает список. */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left lg:pointer-events-none"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-ink">Recent earthquakes</span>
          <span className="block truncate text-xs text-dim lg:hidden">
            {latest
              ? `Latest: M ${latest.mag.toFixed(1)} · ${latest.place}`
              : error
                ? 'Could not load'
                : 'Loading…'}
          </span>
        </span>
        <span className="text-dim lg:hidden">{open ? '▲' : '▼'}</span>
      </button>

      <div className={`${open ? 'block' : 'hidden'} max-h-[70vh] overflow-y-auto px-4 pb-3 lg:block lg:max-h-none lg:flex-1`}>
        {/* Глобус: все землетрясения за сутки. Тёмный фон — чтобы Земля читалась как в космосе. */}
        <div ref={globeBoxRef} className="mb-3 flex justify-center rounded-xl bg-black/40">
          <div style={{ width: globeSize, height: globeSize }}>
            {/* Пока панель свёрнута (телефон), ширина равна 0 и глобус не создаётся. */}
            {hasCoordinates && globeSize > 0 && (
              <Suspense fallback={null}>
                <QuakeGlobe
                  quakes={data?.events ?? []}
                  selectedId={selectedId}
                  onSelect={(q) => setSelectedId(q.id)}
                  size={globeSize}
                />
              </Suspense>
            )}
          </div>
        </div>

        <p className="mb-2 text-xs text-dim">
          {selected
            ? `Selected: M ${selected.mag.toFixed(1)} · ${selected.place} · ${timeAgo(selected.time, now)} · depth ${Math.round(selected.depth_km)} km`
            : 'Globe: every earthquake of the past 24 hours. Drag to turn, click a dot for details.'}
        </p>

        <p className="mb-2 text-xs font-semibold text-dim">
          Latest, magnitude {MIN_MAGNITUDE.toFixed(1)}+
        </p>

        {!data && !error && <p className="text-sm text-dim">Loading earthquakes…</p>}

        {!data && error && (
          <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            Could not load earthquake data. We will try again in a few minutes.
          </p>
        )}

        {data && (
          <>
            {(error || data.stale) && (
              <p role="alert" className="mb-2 rounded-lg border border-amber-400/60 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
                {data.source === 'sample'
                  ? 'The live feed is offline. Showing a saved sample earthquake.'
                  : 'The live feed is not responding. Showing the last data received.'}
              </p>
            )}

            <ul className="flex flex-col gap-2">
              {quakes.map((quake) => (
                <QuakeRow
                  key={quake.id}
                  quake={quake}
                  now={now}
                  selected={quake.id === selectedId}
                  onSelect={(q) => setSelectedId(q.id === selectedId ? null : q.id)}
                />
              ))}
            </ul>

            <p className="mt-2 text-xs text-dim">
              {data.updated_at
                ? `Last updated ${clockTime(data.updated_at * 1000)} · refreshes every 5 minutes`
                : 'Not updated yet'}
            </p>
          </>
        )}
      </div>
    </aside>
  )
}
