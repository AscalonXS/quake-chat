import { useEffect, useRef, useState } from 'react'
import { ask } from './api'
import { EarthquakePanel } from './EarthquakePanel'
import { MessageBubble } from './MessageBubble'
import type { Message } from './types'

export default function App() {
  // Состояние: всё, что меняется на экране, живёт здесь.
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isWaiting, setIsWaiting] = useState(false)

  // Ссылка на невидимый элемент в конце ленты — к нему прокручиваем.
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function send() {
    const question = input.trim()
    if (!question || isWaiting) return

    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', text: question }
    const botMessage: Message = { id: crypto.randomUUID(), role: 'assistant', text: '', status: 'pending' }

    // Заменяет сообщение бота в списке на новую версию.
    const updateBotMessage = (changes: Partial<Message>) =>
      setMessages((prev) => prev.map((m) => (m.id === botMessage.id ? { ...m, ...changes } : m)))

    // Сразу показываем вопрос и «пустой» ответ с индикатором ожидания.
    setMessages((prev) => [...prev, userMessage, botMessage])
    setInput('')
    setIsWaiting(true)

    try {
      const response = await ask(question)
      // Ответ пришёл — подставляем текст, источники и флаг grounded.
      updateBotMessage({
        status: undefined,
        text: response.answer,
        sources: response.sources,
        grounded: response.grounded,
      })
    } catch (error) {
      // Запрос не удался — показываем понятное сообщение вместо ответа.
      updateBotMessage({
        status: 'error',
        text: error instanceof Error ? error.message : 'Please try again.',
      })
    } finally {
      setIsWaiting(false)
    }
  }

  return (
    <div className="flex h-full flex-col bg-page text-ink">
      {/* Баннер с экстренными номерами — виден всегда */}
      <div className="bg-red-600 px-4 py-2 text-center text-sm font-medium text-white">
        Emergency in Korea: <a className="font-bold underline" href="tel:119">119</a> fire &amp; ambulance
        {' · '}
        <a className="font-bold underline" href="tel:112">112</a> police
      </div>

      <header className="border-b border-line bg-surface px-4 py-3">
        <h1 className="text-base font-semibold">Earthquake Preparedness Assistant</h1>
      </header>

      {/* На ноутбуке чат слева, панель справа. На телефоне панель сверху, свёрнутая. */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row-reverse">
        <EarthquakePanel />

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <main className="flex-1 overflow-y-auto px-4 py-6">
            <div className="mx-auto flex max-w-2xl flex-col gap-3">
              {messages.length === 0 && (
                <p className="mt-16 text-center text-dim">
                  Ask how to prepare for an earthquake, or what to do during and after one.
                </p>
              )}

              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}

              <div ref={bottomRef} />
            </div>
          </main>

          <footer className="border-t border-line bg-surface px-4 py-3">
            <form
              className="mx-auto flex max-w-2xl gap-2"
              onSubmit={(e) => {
                e.preventDefault()
                send()
              }}
            >
              <input
                className="min-w-0 flex-1 rounded-xl border border-line bg-page px-4 py-3 text-ink outline-none placeholder:text-dim focus:border-accent"
                placeholder="Type your question"
                aria-label="Your question"
                value={input}
                onChange={(e) => setInput(e.target.value)}
              />
              <button
                type="submit"
                disabled={!input.trim() || isWaiting}
                className="rounded-xl bg-accent px-5 py-3 font-medium text-on-accent disabled:opacity-40"
              >
                Send
              </button>
            </form>
          </footer>
        </div>
      </div>
    </div>
  )
}
