import { Bot, MessageSquarePlus, Send, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button, Card, RiskBadge, StatusBadge } from '../components/ui'
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
    <div className="flex gap-3">
      <div className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-600 text-white"><Bot className="size-4" aria-hidden /></div>
      <div className="min-w-0 flex-1 rounded-xl border border-line bg-white p-4 shadow-sm">
        <p className="text-sm text-ink">{answer.summary}</p>
        {s.simulation && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-ink-2">
            <RiskBadge level={s.simulation.risk_level} /> Simulated: {s.simulation.scenario}
          </div>
        )}
        {SECTIONS.map(([key, title]) => answer[key]?.length ? (
          <div key={key} className="mt-3">
            <h3 className="text-xs font-semibold tracking-wide text-ink-3 uppercase">{title}</h3>
            <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-ink-2">{answer[key].map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        ) : null)}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs text-ink-3">
          <span>Answered by {PROVIDER[message.provider] ?? message.provider}</span>
          {s.fallback_reason && <StatusBadge tone="info">{s.fallback_reason}</StatusBadge>}
          {s.sources?.map((src) => <span key={src.doc} className="rounded bg-slate-100 px-1.5 py-0.5">{src.title}</span>)}
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
    <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
      <Card title="Conversations" className="hidden lg:block" action={
        <button type="button" className="rounded p-1 text-ink-3 hover:bg-slate-100" aria-label="New conversation" onClick={() => { setConversationId(null); setMessages([]) }}>
          <MessageSquarePlus className="size-4" />
        </button>
      }>
        <ul className="space-y-1 text-sm">
          {(conversations.data ?? []).map((c) => (
            <li key={c.id} className={`group flex items-center gap-1 rounded-lg ${c.id === conversationId ? 'bg-brand-50' : 'hover:bg-slate-50'}`}>
              <button type="button" className="min-w-0 flex-1 truncate px-2 py-1.5 text-left text-ink-2" onClick={() => open(c.id)}>{c.title}</button>
              <button type="button" className="rounded p-1 text-ink-3 opacity-0 group-hover:opacity-100 hover:text-red-700" aria-label={`Delete ${c.title}`} onClick={() => remove(c.id)}><Trash2 className="size-3.5" /></button>
            </li>
          ))}
          {!conversations.data?.length && <li className="text-ink-3">No conversations yet.</li>}
        </ul>
      </Card>

      <div className="flex min-h-[70vh] flex-col">
        <div className="mb-4">
          <h1 className="text-2xl font-semibold text-ink">AI Financial Coach</h1>
          <p className="mt-1 text-sm text-ink-2">Answers use your own data and FinTwin's calculations. Every number comes from the app — the coach explains, it doesn't make figures up.</p>
        </div>
        <div className="flex-1 space-y-4">
          {messages.length === 0 && (
            <div className="grid gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((q) => (
                <button key={q} type="button" onClick={() => send(q)} className="rounded-xl border border-line bg-white p-3 text-left text-sm text-ink-2 shadow-sm hover:border-brand-500">{q}</button>
              ))}
            </div>
          )}
          {messages.map((m) => m.role === 'user' ? (
            <div key={m.id} className="flex justify-end"><div className="max-w-[80%] rounded-xl bg-brand-600 px-4 py-2.5 text-sm text-white">{m.content}</div></div>
          ) : <AssistantMessage key={m.id} message={m} />)}
          {busy && <p className="text-sm text-ink-3" role="status">Calculating…</p>}
          <div ref={bottom} />
        </div>
        {error && <p className="mt-3 text-sm text-red-700" role="alert">{error}</p>}
        <form onSubmit={(e) => { e.preventDefault(); send(input) }} className="sticky bottom-0 mt-4 flex gap-2 bg-page py-3">
          <input
            value={input} onChange={(e) => setInput(e.target.value)} maxLength={1000} aria-label="Ask the coach"
            placeholder="Ask about your money, e.g. “What if my income falls by 20%?”"
            className="flex-1 rounded-lg border border-line bg-white px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
          />
          <Button type="submit" loading={busy} disabled={!input.trim()}><Send className="size-4" /> Ask</Button>
        </form>
        <p className="text-xs text-ink-3">FinTwin is a decision-support and educational tool, not a licensed financial advisor.</p>
      </div>
    </div>
  )
}
