import type { ChatResponse, EarthquakesResponse } from './types'

// Заглушка вместо бэкенда. Возвращает данные в том же виде, что и POST /api/chat,
// поэтому на шаге 4 заменится только эта функция.
//
// Чтобы можно было посмотреть все состояния экрана без бэкенда:
//   вопрос со словом "tomorrow" — ответа в документах нет (grounded: false)
//   вопрос со словом "error"    — запрос падает с ошибкой

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export async function askFake(question: string): Promise<ChatResponse> {
  await sleep(900) // имитация ожидания ответа от сервера

  const q = question.toLowerCase()

  if (q.includes('error')) {
    throw new Error('Something went wrong on our side. Please try again.')
  }

  if (q.includes('tomorrow')) {
    return {
      answer:
        'I could not find this in the documents. Emergency: 119 (Korea fire/rescue), 112 (police).',
      sources: [],
      grounded: false,
    }
  }

  return {
    answer:
      '[FAKE] During an earthquake: drop to your hands and knees, take cover under a sturdy table, and hold on until the shaking stops.',
    sources: [
      {
        title: 'Earthquake Safety Guide',
        page: 4,
        snippet: 'Drop, Cover, and Hold On is the recommended action during shaking.',
      },
      {
        title: 'Household Preparedness Handbook',
        page: 12,
        snippet: 'Stay away from windows and heavy furniture that could fall.',
      },
    ],
    grounded: true,
  }
}

export async function getEarthquakesFake(): Promise<EarthquakesResponse> {
  await sleep(300)
  const now = Date.now()
  return {
    events: [
      { id: 'fake-1', mag: 5.4, place: '10 km NE of Gyeongju, South Korea', depth_km: 12, time: now - 14 * 60_000, url: null, lat: 35.9, lon: 129.3 },
      { id: 'fake-2', mag: 4.1, place: '65 km S of Ugashik, Alaska', depth_km: 1.2, time: now - 55 * 60_000, url: null, lat: 56.9, lon: -157.4 },
      { id: 'fake-3', mag: 2.9, place: '42 km N of Kernville, CA', depth_km: 6, time: now - 3 * 3_600_000, url: null, lat: 36.1, lon: -118.4 },
    ],
    updated_at: now / 1000,
    source: 'usgs',
    stale: false,
  }
}
