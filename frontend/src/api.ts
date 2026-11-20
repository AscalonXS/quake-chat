import { askFake, getEarthquakesFake } from './fakeApi'
import type { ChatResponse, EarthquakesResponse } from './types'

// Адрес бэкенда. Можно поменять в файле .env: VITE_API_URL=http://localhost:8000
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// Запасной режим на случай, если бэкенд не запущен: VITE_USE_FAKE=true в файле .env
const USE_FAKE = import.meta.env.VITE_USE_FAKE === 'true'

// Общая функция запроса: отправляет, ждёт не дольше 30 секунд,
// а любую неудачу превращает в понятный текст для пользователя.
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_URL + path, { ...init, signal: AbortSignal.timeout(30_000) })
  } catch {
    throw new Error('Cannot reach the server. Check your connection and try again.')
  }

  if (!response.ok) {
    // Бэкенд присылает {"detail": "текст"}; при ошибке проверки данных detail — список.
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.')
  }

  return response.json()
}

export function ask(question: string): Promise<ChatResponse> {
  if (USE_FAKE) return askFake(question)
  return request('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

export function getEarthquakes(): Promise<EarthquakesResponse> {
  if (USE_FAKE) return getEarthquakesFake()
  return request('/api/earthquakes')
}
