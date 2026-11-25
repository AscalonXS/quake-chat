// Один источник, на который ссылается ответ.
export type Source = {
  title: string
  page: number
  snippet: string
}

// То, что бэкенд возвращает на вопрос (POST /api/chat в контракте Damir).
export type ChatResponse = {
  answer: string
  sources: Source[]
  grounded: boolean // false — ответа в документах нет
}

// Одно сообщение в ленте чата.
export type Message = {
  id: string
  role: 'user' | 'assistant'
  text: string
  status?: 'pending' | 'error' // ждём ответ / запрос не удался
  sources?: Source[]
  grounded?: boolean
}

// Одно землетрясение из ленты (GET /api/earthquakes).
export type Quake = {
  id: string
  mag: number
  place: string
  depth_km: number
  time: number // Unix-время в миллисекундах
  url: string | null
  // Координаты для глобуса. Бэкенд их пока не присылает — тогда берём из ленты USGS напрямую.
  lat?: number
  lon?: number
}

export type EarthquakesResponse = {
  events: Quake[]
  updated_at: number | null // Unix-время в секундах; null — показан сохранённый пример
  source: 'usgs' | 'sample'
  stale: boolean // true — лента недоступна, данные старые
}
