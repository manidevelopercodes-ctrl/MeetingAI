import { useState } from 'react'
import { askQuestion } from '../services/api.js'
import { formatTime } from './Transcript.jsx'

const SUGGESTIONS = [
  'What were the main topics?',
  'What decisions were made?',
  'What action items were assigned?',
  'Why was this approach selected?',
  'Give me a short summary.',
]

export default function Chat({ meetingId, enabled }) {
  const [turns, setTurns] = useState([])
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function ask(text) {
    const trimmed = text.trim()
    if (!trimmed || busy) return

    setBusy(true)
    setError(null)
    setQuestion('')
    try {
      const response = await askQuestion(meetingId, trimmed)
      setTurns((previous) => [
        ...previous,
        { question: trimmed, answer: response.answer, sources: response.sources || [] },
      ])
    } catch (askError) {
      setError(askError.message)
    } finally {
      setBusy(false)
    }
  }

  if (!enabled) {
    return (
      <div className="empty small">
        Chat becomes available once processing is COMPLETED.
      </div>
    )
  }

  return (
    <div>
      {turns.length === 0 && (
        <p className="small muted">
          Ask anything about this meeting. Answers come only from its transcript.
        </p>
      )}

      <div className="suggestions">
        {SUGGESTIONS.map((text) => (
          <button key={text} onClick={() => ask(text)} disabled={busy}>
            {text}
          </button>
        ))}
      </div>

      <div className="chat-log">
        {turns.map((turn, index) => (
          <div className="chat-turn" key={index}>
            <div className="question">{turn.question}</div>
            <div className="answer">{turn.answer}</div>

            {turn.sources.length > 0 && (
              <div className="sources">
                <div className="small muted"><strong>Transcript sources</strong></div>
                {turn.sources.map((source, sourceIndex) => (
                  <div className="source" key={sourceIndex}>
                    [{formatTime(source.start_time)} - {formatTime(source.end_time)}]{' '}
                    {source.speaker}: {source.text}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {busy && (
        <p className="muted small">
          <span className="spinner" /> Thinking...
        </p>
      )}
      {error && <div className="alert error">{error}</div>}

      <form
        className="chat-form"
        onSubmit={(event) => {
          event.preventDefault()
          ask(question)
        }}
      >
        <input
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about this meeting"
          disabled={busy}
        />
        <button type="submit" className="primary" disabled={busy || !question.trim()}>
          Ask
        </button>
      </form>
    </div>
  )
}
