import { ArrowUpRight, Bot, MessageSquarePlus, Send, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button, RiskBadge, StatusBadge } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api, errorText } from '../services/api'

const SUGGESTIONS = [
  'Can I afford a ₹1,30,000 laptop?',
  'Why did my financial health score decrease?',
  'Where am I overspending?',
  'How much should I save each month for my car goal?',
  'Why is my emergency fund weak?',
  'What happens if I increase my SIP by ₹5,000?',
  'How can I improve my financial health?',
  'What happens if I take a ₹5 lakh loan?',
]
const SECTIONS = [
  ['facts', 'Your data'],
  ['calculations', 'Calculations'],
  ['predictions', 'Estimates & projections'],
  ['recommendations', 'What you could do'],
  ['background', 'Background'],
]
const PROVIDER = { local: 'FinTwin engine', openai: 'OpenAI', gemini: 'Gemini' }

function AssistantMessage({ message }) {
  const s = message.structured ?? {}
  const answer = s.answer ?? { summary: message.content }
  return (
    <div className="reveal flex gap-3">
      <div className="grid size-8 shrink-0 place-items-center rounded-md bg-ink text-white"><Bot className="size-4" strokeWidth={1.75} aria-hidden /></div>
      <div className="min-w-0 flex-1 rounded-xl rounded-tl-sm border border-line bg-white p-5">
        <p className="text-[15px] leading-relaxed text-ink">{answer.summary}</p>
        {s.simulation && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md bg-surface px-3 py-2 text-xs text-ink-2">
            <RiskBadge level={s.simulation.risk_level} /> <span className="font-mono text-[11px] text-ink-3">simulated</span> {s.simulation.scenario}
          </div>
        )}
        {SECTIONS.map(([key, title]) => answer[key]?.length ? (
          <div key={key} className="mt-4">
            <h3 className="font-mono text-[11px] text-ink-3">{title}</h3>
            <ul className="mt-1.5 space-y-1.5 text-sm text-ink-2">
              {answer[key].map((item) => (
                <li key={item} className="flex gap-2.5"><span className="mt-2 size-1 shrink-0 rounded-full bg-ink-3" aria-hidden />{item}</li>
              ))}
            </ul>
          </div>
        ) : null)}
        <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs text-ink-3">
          <span>Answered by {PROVIDER[message.provider] ?? message.provider}</span>
          {s.fallback_reason && <StatusBadge tone="info">{s.fallback_reason}</StatusBadge>}
          {s.sources?.map((src) => <span key={src.doc} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px]">{src.title}</span>)}
        </div>
      </div>
    </div>
  )
}

export default function Coach() {
  const conversations = useApi('/coach/conversations')
  const [conversationId, setConversationId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const bottom = useRef(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  async function open(id) {
    setError('')
    const { data } = await api.get(`/coach/conversations/${id}`)
    setConversationId(id)
    setMessages(data.messages)
  }

  async function send(text) {
    const message = text.trim()
    if (!message || busy) return
    setBusy(true)
    setError('')
    setInput('')
    setMessages((m) => [...m, { id: `pending-${Date.now()}`, role: 'user', content: message }])
    try {
      const { data } = await api.post('/coach/chat', { message, conversation_id: conversationId })
      setConversationId(data.conversation_id)
      setMessages((m) => [...m, {
        id: data.message_id, role: 'assistant', content: data.text, provider: data.provider,
        structured: { answer: data.answer, sources: data.sources, simulation: data.simulation, fallback_reason: data.fallback_reason },
      }])
      if (!conversationId) conversations.reload()
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id) {
    await api.del(`/coach/conversations/${id}`)
    if (id === conversationId) { setConversationId(null); setMessages([]) }
    conversations.reload()
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[15rem_1fr]">
      <aside className="hidden self-start lg:sticky lg:top-6 lg:block" aria-label="Conversations">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-mono text-[11px] text-ink-3">Conversations</h2>
          <button type="button" className="grid size-8 place-items-center rounded-md text-ink-3 transition duration-200 hover:bg-white hover:text-ink" aria-label="New conversation" onClick={() => { setConversationId(null); setMessages([]) }}>
            <MessageSquarePlus className="size-4" strokeWidth={1.75} />
          </button>
        </div>
        <ul className="space-y-0.5 text-sm">
          {(conversations.data ?? []).map((c) => (
            <li key={c.id} className={`group flex items-center gap-1 rounded-md transition duration-200 ${c.id === conversationId ? 'bg-white shadow-[0_0_0_1px_var(--color-line)]' : 'hover:bg-white/70'}`}>
              <button type="button" className={`min-w-0 flex-1 truncate px-3 py-2 text-left ${c.id === conversationId ? 'text-ink' : 'text-ink-2'}`} onClick={() => open(c.id)}>{c.title}</button>
              <button type="button" className="mr-1 grid size-7 place-items-center rounded text-ink-3 opacity-0 transition group-hover:opacity-100 hover:text-red-700 focus-visible:opacity-100" aria-label={`Delete ${c.title}`} onClick={() => remove(c.id)}><Trash2 className="size-3.5" strokeWidth={1.75} /></button>
            </li>
          ))}
          {!conversations.data?.length && <li className="px-3 py-2 text-ink-3">No conversations yet.</li>}
        </ul>
      </aside>

      <div className="flex min-h-[75dvh] flex-col">
        <div className="mb-8">
          <h1 className="font-serif text-[2.25rem] leading-[1.1] tracking-[-0.02em] text-ink">AI Financial Coach</h1>
          <p className="mt-2 max-w-2xl text-sm text-ink-2">Answers use your own data and FinTwin's calculations. The coach explains the numbers; every figure comes from the app, never from the language model.</p>
        </div>
        <div className="flex-1 space-y-5">
          {messages.length === 0 && (
            <div>
              <p className="mb-3 font-mono text-[11px] text-ink-3">Try asking</p>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {SUGGESTIONS.map((q, i) => (
                  <button
                    key={q} type="button" onClick={() => send(q)} style={{ '--i': i }}
                    className="reveal group flex items-start justify-between gap-3 rounded-xl border border-line bg-white px-4 py-3.5 text-left text-sm text-ink-2 transition duration-200 ease-out-soft hover:border-ink/20 hover:text-ink hover:shadow-lift active:scale-[0.99]"
                  >
                    {q}
                    <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-ink-3 transition duration-200 ease-out-soft group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-ink" strokeWidth={1.75} aria-hidden />
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) => m.role === 'user' ? (
            <div key={m.id} className="reveal flex justify-end"><div className="max-w-[80%] rounded-xl rounded-br-sm bg-ink px-4 py-2.5 text-sm text-white">{m.content}</div></div>
          ) : <AssistantMessage key={m.id} message={m} />)}
          {busy && (
            <div className="flex items-center gap-3 text-sm text-ink-3" role="status">
              <div className="grid size-8 place-items-center rounded-md bg-ink text-white"><Bot className="size-4" strokeWidth={1.75} aria-hidden /></div>
              <span className="flex gap-1" aria-hidden>
                <span className="size-1.5 animate-pulse rounded-full bg-ink-3" />
                <span className="size-1.5 animate-pulse rounded-full bg-ink-3 [animation-delay:150ms]" />
                <span className="size-1.5 animate-pulse rounded-full bg-ink-3 [animation-delay:300ms]" />
              </span>
              Checking your numbers…
            </div>
          )}
          <div ref={bottom} />
        </div>
        {error && <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">{error}</p>}
        <form onSubmit={(e) => { e.preventDefault(); send(input) }} className="sticky bottom-0 mt-6 bg-page/90 pt-3 pb-4 backdrop-blur-md">
          <div className="flex items-center gap-2 rounded-xl border border-line bg-white p-1.5 pl-4 transition duration-200 focus-within:border-ink/40 focus-within:ring-4 focus-within:ring-ink/5">
            <input
              value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000} aria-label="Ask the coach"
              placeholder="Ask about your money, e.g. “What if my income falls by 20%?”"
              className="min-w-0 flex-1 bg-transparent py-1.5 text-sm text-ink outline-none placeholder:text-ink-3"
            />
            <Button type="submit" loading={busy} disabled={!input.trim()}><Send className="size-4" strokeWidth={1.75} /> Ask</Button>
          </div>
          <p className="mt-2 text-xs text-ink-3">FinTwin is a decision-support and educational tool, not a licensed financial advisor.</p>
        </form>
      </div>
    </div>
  )
}
