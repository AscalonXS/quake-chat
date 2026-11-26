import type { Message } from './types'

// Одно сообщение в ленте. Вид зависит от того, кто написал и в каком оно состоянии.
export function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="max-w-[85%] self-end rounded-2xl rounded-br-sm bg-accent px-4 py-2 break-words whitespace-pre-wrap text-on-accent">
        {message.text}
      </div>
    )
  }

  // Ждём ответ
  if (message.status === 'pending') {
    return (
      <div
        role="status"
        className="self-start rounded-2xl rounded-bl-sm border border-line bg-surface px-4 py-2 text-dim"
      >
        <span className="animate-pulse">Searching the documents…</span>
      </div>
    )
  }

  // Запрос не удался
  if (message.status === 'error') {
    return (
      <div
        role="alert"
        className="max-w-[85%] self-start rounded-2xl rounded-bl-sm border border-red-500/50 bg-red-500/10 px-4 py-2 break-words text-red-200"
      >
        <p className="font-semibold">Could not get an answer</p>
        <p className="text-sm">{message.text}</p>
      </div>
    )
  }

  // Ответа в документах нет
  if (message.grounded === false) {
    return (
      <div className="max-w-[85%] self-start rounded-2xl rounded-bl-sm border border-dashed border-amber-400/60 bg-amber-400/10 px-4 py-2 break-words whitespace-pre-wrap text-amber-100">
        <p className="mb-1 text-xs font-semibold tracking-wide uppercase">Not found in the documents</p>
        {message.text}
      </div>
    )
  }

  // Обычный ответ с источниками
  return (
    <div className="flex max-w-[85%] flex-col gap-2 self-start">
      <div className="rounded-2xl rounded-bl-sm border border-line bg-surface px-4 py-2 break-words whitespace-pre-wrap">
        {message.text}
      </div>

      {message.sources && message.sources.length > 0 && (
        <div className="rounded-xl border border-line bg-surface px-3 py-2 text-sm">
          <p className="mb-1 text-xs font-semibold tracking-wide text-accent uppercase">Sources</p>
          <ol className="flex flex-col gap-1.5">
            {message.sources.map((source, i) => (
              <li key={i} className="break-words">
                <span className="font-medium text-ink">
                  {i + 1}. {source.title}, p. {source.page}
                </span>
                <span className="block text-dim">“{source.snippet}”</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
