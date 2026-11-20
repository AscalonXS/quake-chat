import { useEffect, useState } from 'react'
import type { Quake } from './types'
import { useEarthquakes } from './useEarthquakes'

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
  return 'bg-slate-200 text-slate-800'
}

function QuakeRow({ quake, now }: { quake: Quake; now: number }) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2">
      <span
        className={`w-12 shrink-0 rounded-md py-1 text-center text-sm font-bold ${magnitudeColor(quake.mag)}`}
      >
        {quake.mag.toFixed(1)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm break-words text-slate-900">{quake.place}</span>
        <span className="block text-xs text-slate-500">
          {timeAgo(quake.time, now)} · depth {Math.round(quake.depth_km)} km
        </span>
      </span>
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

  return (
    <aside className="shrink-0 border-b border-slate-200 bg-slate-100 lg:flex lg:w-80 lg:flex-col lg:border-b-0 lg:border-l">
      {/* Заголовок. На телефоне это кнопка, которая раскрывает список. */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left lg:pointer-events-none"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-900">Recent earthquakes</span>
          <span className="block truncate text-xs text-slate-600 lg:hidden">
            {latest
              ? `Latest: M ${latest.mag.toFixed(1)} · ${latest.place}`
              : error
                ? 'Could not load'
                : 'Loading…'}
          </span>
        </span>
        <span className="text-slate-500 lg:hidden">{open ? '▲' : '▼'}</span>
      </button>

      <div className={`${open ? 'block' : 'hidden'} max-h-72 overflow-y-auto px-4 pb-3 lg:block lg:max-h-none lg:flex-1`}>
        <p className="mb-2 text-xs text-slate-500">
          Worldwide, past 24 hours, magnitude {MIN_MAGNITUDE.toFixed(1)}+
        </p>

        {!data && !error && <p className="text-sm text-slate-500">Loading earthquakes…</p>}

        {!data && error && (
          <p role="alert" className="rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800">
            Could not load earthquake data. We will try again in a few minutes.
          </p>
        )}

        {data && (
          <>
            {(error || data.stale) && (
              <p role="alert" className="mb-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                {data.source === 'sample'
                  ? 'The live feed is offline. Showing a saved sample earthquake.'
                  : 'The live feed is not responding. Showing the last data received.'}
              </p>
            )}

            <ul className="flex flex-col gap-2">
              {quakes.map((quake) => (
                <QuakeRow key={quake.id} quake={quake} now={now} />
              ))}
            </ul>

            <p className="mt-2 text-xs text-slate-500">
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
