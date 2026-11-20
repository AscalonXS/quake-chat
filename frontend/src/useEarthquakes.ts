import { useEffect, useState } from 'react'
import { getEarthquakes } from './api'
import type { EarthquakesResponse } from './types'

// Как часто обновлять панель. Бэкенд сам хранит ленту 5 минут, чаще спрашивать нет смысла.
const REFRESH_MS = 5 * 60_000

// Загружает ленту землетрясений и сама обновляет её по таймеру.
// Если очередной запрос не удался, остаются последние полученные данные.
export function useEarthquakes() {
  const [data, setData] = useState<EarthquakesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const response = await getEarthquakes()
        if (cancelled) return
        setData(response)
        setError(null)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Could not load earthquakes.')
      }
    }

    load()
    const timer = setInterval(load, REFRESH_MS)

    // Когда панель убирается с экрана, останавливаем таймер.
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return { data, error }
}
