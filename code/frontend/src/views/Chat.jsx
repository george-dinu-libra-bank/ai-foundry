import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Err, RunsOnBadge } from '../components'

// The backend is stateless: /ask takes one question and remembers nothing. Holding a
// conversation is therefore this component's job. We keep the transcript and replay a
// short window of it in front of the new question, so "and what does that cost?" has
// something to refer to.
//
// Only the last TURNS_SENT exchanges are replayed, and each answer is truncated: the
// whole point of the retrieval work is that the context budget goes to retrieved
// passages, and an unbounded transcript would eat it. Four turns is enough for the
// follow-ups people actually ask and costs a few hundred tokens.
const TURNS_SENT = 4
const REPLY_CHARS = 400

function withHistory(turns, question) {
  if (turns.length === 0) return question
  const transcript = turns
    .slice(-TURNS_SENT)
    .map(({ q, a }) => `Customer: ${q}\nLibra Assist: ${a.slice(0, REPLY_CHARS)}`)
    .join('\n\n')
  return (
    'CONVERSATION SO FAR — for resolving references like "it", "that card" or ' +
    '"the fee you mentioned". Do not treat it as a source; only the CONTEXT ' +
    'passages are sources.\n' +
    `${transcript}\n\n` +
    `Customer's new question:\n${question}`
  )
}

// A refusal is a success, not an error — but only if the interface says so. These are
// the shapes a refusal takes; matching them lets the UI label the turn instead of
// showing a wall of text that looks like an answer.
const REFUSAL_HINTS = [
  "no relevant", "no passages", "not in the", "no information", "don't have",
  "do not have", "can't find", "cannot find", "does not contain", "not covered",
  "can't answer", "cannot answer", "not include", "no mention", "outside the scope",
]

function looksLikeRefusal(text) {
  const t = text.toLowerCase().replace(/[‘’]/g, "'")
  return REFUSAL_HINTS.some((h) => t.includes(h))
}

export default function Chat({ agents, hostedOnly = [], foundry }) {
  const [messages, setMessages] = useState([])
  const [turns, setTurns] = useState([])            // [{ q, a }] — what gets replayed
  const [question, setQuestion] = useState('')
  const [agent, setAgent] = useState('default')
  const [useRag, setUseRag] = useState(true)
  const [mode, setMode] = useState('local')
  const [topK, setTopK] = useState(6)
  const [multiTurn, setMultiTurn] = useState(true)
  const [showDials, setShowDials] = useState(false)
  // Retrieval dials. `null` means "whatever the backend's .env says", which is the
  // calibrated configuration; the controls exist so a reviewer can turn each one off
  // and watch the answer change.
  const [minScore, setMinScore] = useState(null)
  const [currentOnly, setCurrentOnly] = useState(null)
  const [hybrid, setHybrid] = useState(null)
  const [dedup, setDedup] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, busy])

  async function send() {
    const text = question.trim()
    if (!text || busy) return
    setQuestion(''); setError(null); setBusy(true)
    setMessages((m) => [...m, { role: 'user', text }])

    const payload = {
      question: multiTurn ? withHistory(turns, text) : text,
      use_rag: useRag, top_k: Number(topK), agent, agent_mode: mode,
    }
    if (useRag) {
      if (minScore !== null) payload.min_score = minScore
      if (currentOnly !== null) payload.filters = currentOnly ? { status: 'current' } : {}
      if (hybrid !== null) payload.hybrid = hybrid
      if (dedup !== null) payload.dedup = dedup
    }

    try {
      const data = await api.ask(payload)
      setMessages((m) => [...m, { role: 'bot', data, asked: text }])
      setTurns((t) => [...t, { q: text, a: data.answer }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'err', text: e.message }])
      setError(e.message)
    } finally { setBusy(false) }
  }

  function clearChat() {
    setMessages([]); setTurns([]); setError(null)
  }

  const all = [...agents, ...hostedOnly]
  const current = all.find((a) => a.name === agent)

  // Where this agent CAN run decides which lanes are offered.
  const hostedKnown = foundry?.available
  const isHosted = current?.runs_on === 'both' || current?.runs_on === 'foundry'
  const localImpossible = current?.runs_on === 'foundry'      // no JSON file to run here
  const foundryBlocked = hostedKnown && !isHosted             // definitely not deployed

  // Keep the mode legal whenever the selected agent changes.
  useEffect(() => {
    if (localImpossible && mode !== 'foundry') setMode('foundry')
    else if (foundryBlocked && mode === 'foundry') setMode('local')
  }, [agent, localImpossible, foundryBlocked])   // eslint-disable-line react-hooks/exhaustive-deps

  const dialsChanged = [minScore, currentOnly, hybrid, dedup].some((v) => v !== null)

  return (
    <div className="chat-wrap">
      <div className="chat-bar">
        <select value={agent} onChange={(e) => setAgent(e.target.value)} title="Which persona answers">
          {agents.map((a) => <option key={a.name} value={a.name}>{a.display_name}</option>)}
          {hostedOnly.length > 0 && (
            <optgroup label="hosted in Foundry only">
              {hostedOnly.map((a) => <option key={a.name} value={a.name}>{a.display_name}</option>)}
            </optgroup>
          )}
        </select>
        {current && <RunsOnBadge runsOn={current.runs_on} reason={foundry?.reason} />}
        <label className="check" style={{ margin: 0 }}>
          <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
          use RAG
        </label>
        <label className="check" style={{ margin: 0 }}
               title="Replay the last few exchanges so follow-up questions resolve. The backend keeps no state.">
          <input type="checkbox" checked={multiTurn} onChange={(e) => setMultiTurn(e.target.checked)} />
          memory
        </label>
        <select value={mode} onChange={(e) => setMode(e.target.value)} style={{ minWidth: '9rem' }}
                title="Where the loop executes">
          <option value="local" disabled={localImpossible}
                  title={localImpossible ? 'This agent has no local JSON file' : ''}>
            local agent
          </option>
          <option value="foundry" disabled={foundryBlocked}
                  title={foundryBlocked ? 'Not deployed to Foundry — deploy it from the Agents view' : ''}>
            Foundry agent{foundryBlocked ? ' — not deployed' : ''}
          </option>
        </select>
        <input type="number" min="1" max="10" value={topK} onChange={(e) => setTopK(e.target.value)}
               style={{ width: '4.5rem', flex: '0 0 auto' }} title="Passages to retrieve" />
        <button className={`btn btn-sm ${dialsChanged ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => setShowDials((s) => !s)} disabled={!useRag}
                title="Turn the retrieval improvements on and off">
          retrieval{dialsChanged ? ' ✱' : ''}
        </button>
        <button className="btn btn-outline btn-sm" onClick={clearChat}>clear</button>
        {current && <span className="badge muted" title={current.description}>temp {current.temperature ?? '—'}</span>}
      </div>

      {showDials && useRag && (
        <div className="chat-bar" style={{ borderTop: 0, flexWrap: 'wrap' }}>
          <span className="muted" style={{ fontSize: '.78rem' }}>
            unset = the backend default from .env (the calibrated setup)
          </span>
          <Dial label="score floor" value={minScore} onChange={setMinScore}
                options={[['off', 0], ['0.45', 0.45], ['0.55', 0.55]]}
                title="If nothing scores above the floor, retrieval returns nothing and the assistant says so" />
          <Dial label="current only" value={currentOnly} onChange={setCurrentOnly}
                options={[['no', false], ['yes', true]]}
                title="Filter out superseded documents — the 2025 fee schedule and limits" />
          <Dial label="hybrid" value={hybrid} onChange={setHybrid}
                options={[['off', false], ['on', true]]}
                title="Fuse a keyword arm with the vector arm — finds exact amounts and codes" />
          <Dial label="dedup" value={dedup} onChange={setDedup}
                options={[['off', false], ['on', true]]}
                title="Collapse near-identical chunks" />
          {dialsChanged && (
            <button className="btn btn-outline btn-sm"
                    onClick={() => { setMinScore(null); setCurrentOnly(null); setHybrid(null); setDedup(null) }}>
              reset to defaults
            </button>
          )}
        </div>
      )}

      <div className="msgs">
        {messages.length === 0 && (
          <div className="card" style={{ alignSelf: 'center', maxWidth: '46rem', textAlign: 'center' }}>
            <h3>Libra Assist</h3>
            <p className="muted" style={{ margin: 0 }}>
              Retail card support, grounded in 20 fabricated bank documents. Ask a follow-up
              and it will resolve — the transcript is replayed by this page, since the API
              keeps no state. Switch the persona to change how it answers, or open{' '}
              <strong>retrieval</strong> to turn an improvement off and watch it get worse.
            </p>
            <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap', justifyContent: 'center',
                          marginTop: '.8rem' }}>
              {['How much cash can I withdraw from an ATM per day?',
                'What is the interest rate on your student loans?',
                'The thief spent 900 lei before I reported my card stolen and 400 after — what do I owe?',
              ].map((q) => (
                <button key={q} className="btn btn-outline btn-sm" onClick={() => setQuestion(q)}>
                  {q.length > 46 ? `${q.slice(0, 46)}…` : q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => {
          if (m.role === 'user') return <div className="msg user" key={i}>{m.text}</div>
          if (m.role === 'err') return <div className="msg err" key={i}><strong>Request failed:</strong> {m.text}</div>
          const d = m.data
          const r = d.retrieval
          const nothing = r?.nothing_relevant || (d.augmented && (d.retrieved?.length ?? 0) === 0)
          const refused = looksLikeRefusal(d.answer)
          return (
            <div className="msg bot" key={i}>
              {/* Honest failure: name it before the text, so a refusal is never mistaken
                  for a thin answer and an empty retrieval is never mistaken for a bug. */}
              {nothing && (
                <div className="notice notice-warn">
                  <strong>Nothing relevant found.</strong> The search ran against all 20
                  documents and no passage scored above the floor
                  {r?.min_score ? ` (${r.min_score})` : ''}
                  {r?.filters && Object.keys(r.filters).length > 0
                    ? `, with filters ${JSON.stringify(r.filters)}` : ''}.
                  The answer below is a refusal, not a lookup.
                </div>
              )}
              {!nothing && refused && d.augmented && (
                <div className="notice">
                  <strong>Declined to answer from these passages.</strong> Retrieval returned{' '}
                  {d.retrieved.length} passage{d.retrieved.length === 1 ? '' : 's'}, but the
                  agent judged them insufficient rather than stretching them into an answer.
                </div>
              )}

              {d.answer}

              <div className="msg-meta">
                <span className="badge">{d.agent?.display_name || 'agent'}</span>
                <span className={`badge ${d.augmented ? 'gold' : 'muted'}`}>
                  {d.augmented ? (nothing ? 'grounded — nothing found' : 'grounded') : 'no retrieval'}
                </span>
                <span className="badge muted">{d.agent?.mode}</span>
                <span className="badge muted">{d.model}</span>
                {d.usage && <span className="badge muted">{d.usage.prompt_tokens}↑ {d.usage.completion_tokens}↓ tokens</span>}
                {r?.hybrid && <span className="badge muted" title="Keyword arm fused with the vector arm">hybrid</span>}
                {r?.dedup && <span className="badge muted">dedup</span>}
              </div>

              {d.retrieved?.length > 0 && <Sources hits={d.retrieved} report={r} />}

              <details className="sources">
                <summary>the exact prompt that was sent</summary>
                <pre className="out" style={{ marginTop: '.4rem' }}>{`SYSTEM:\n${d.system_prompt}\n\nUSER:\n${d.prompt_sent}`}</pre>
              </details>
            </div>
          )
        })}
        {busy && <div className="msg bot"><span className="spin" /> thinking…</div>}
        <div ref={endRef} />
      </div>

      <Err error={error} />
      <div className="composer">
        <textarea value={question} placeholder="Ask Libra Assist…  (Enter to send, Shift+Enter for a new line)"
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
        <button className="btn btn-primary" onClick={send} disabled={busy || !question.trim()}>Send</button>
      </div>
    </div>
  )
}

// Which documents grounded the answer, named — a score attached to an anonymous block
// of text tells a reviewer nothing about whether the right document was used.
function Sources({ hits, report }) {
  const docs = [...new Set(hits.map((h) => h.title || h.source))]
  return (
    <details className="sources">
      <summary>
        {docs.length} document{docs.length === 1 ? '' : 's'} grounded this answer
        {report && report.candidates > report.kept &&
          ` · ${report.candidates - report.kept} passage(s) discarded`}
      </summary>

      <div style={{ display: 'flex', gap: '.35rem', flexWrap: 'wrap', margin: '.5rem 0' }}>
        {docs.map((d) => <span className="badge" key={d}>{d}</span>)}
      </div>

      {hits.map((h, j) => (
        <div className="src" key={h.id}>
          <span className="score">
            [{j + 1}] {h.title || h.source} · score {h.score.toFixed(4)}
            {h.status && h.status !== 'current' && ` · ${h.status}`}
            {h.effective && ` · effective ${h.effective}`}
            {h.version != null && ` · v${h.version}`}
            {h.matched?.includes('lexical') && ' · exact match'}
          </span>
          <div>{h.text}</div>
        </div>
      ))}
    </details>
  )
}

function Dial({ label, value, onChange, options, title }) {
  return (
    <label className="check" style={{ margin: 0, gap: '.35rem' }} title={title}>
      <span className="muted" style={{ fontSize: '.78rem' }}>{label}</span>
      <select value={value === null ? '' : String(value)}
              onChange={(e) => onChange(e.target.value === '' ? null
                : options.find(([, v]) => String(v) === e.target.value)[1])}
              style={{ minWidth: '5.5rem' }}>
        <option value="">default</option>
        {options.map(([text, v]) => <option key={text} value={String(v)}>{text}</option>)}
      </select>
    </label>
  )
}
