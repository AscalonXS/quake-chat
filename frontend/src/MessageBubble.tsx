import type { Message } from './types'

// Одно сообщение в ленте. Вид зависит от того, кто написал и в каком оно состоянии.
export function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="max-w-[85%] self-end rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 break-words whitespace-pre-wrap text-white">
        {message.text}
      </div>
    )
  }

  // Ждём ответ
  if (message.status === 'pending') {
    return (
      <div
        role="status"
        className="self-start rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-2 text-slate-500"
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
        className="max-w-[85%] self-start rounded-2xl rounded-bl-sm border border-red-300 bg-red-50 px-4 py-2 break-words text-red-800"
      >
        <p className="font-semibold">Could not get an answer</p>
        <p className="text-sm">{message.text}</p>
      </div>
    )
  }

  // Ответа в документах нет
  if (message.grounded === false) {
    return (
      <div className="max-w-[85%] self-start rounded-2xl rounded-bl-sm border border-dashed border-amber-400 bg-amber-50 px-4 py-2 break-words whitespace-pre-wrap text-amber-900">
        <p className="mb-1 text-xs font-semibold tracking-wide uppercase">Not found in the documents</p>
        {message.text}
      </div>
    )
  }

  // Обычный ответ с источниками
  return (
    <div className="flex max-w-[85%] flex-col gap-2 self-start">
      <div className="rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-4 py-2 break-words whitespace-pre-wrap">
        {message.text}
      </div>

      {message.sources && message.sources.length > 0 && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm">
          <p className="mb-1 text-xs font-semibold tracking-wide text-emerald-800 uppercase">Sources</p>
          <ol className="flex flex-col gap-1.5">
            {message.sources.map((source, i) => (
              <li key={i} className="break-words">
                <span className="font-medium text-slate-900">
                  {i + 1}. {source.title}, p. {source.page}
                </span>
                <span className="block text-slate-600">“{source.snippet}”</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  )
}
