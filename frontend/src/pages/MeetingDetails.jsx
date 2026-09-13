import { useCallback, useEffect, useState } from 'react'
import Chat from '../components/Chat.jsx'
import Summary from '../components/Summary.jsx'
import Transcript from '../components/Transcript.jsx'
import {
  audioUrl,
  getMeeting,
  getSummary,
  getTranscript,
  isProcessing,
  processMeeting,
} from '../services/api.js'

const POLL_INTERVAL_MS = 4000

function badgeClass(status) {
  if (status === 'COMPLETED') return 'badge completed'
  if (status === 'FAILED') return 'badge failed'
  if (isProcessing(status)) return 'badge working'
  return 'badge uploaded'
}

export default function MeetingDetails({ meetingId, onBack }) {
  const [meeting, setMeeting] = useState(null)
  const [segments, setSegments] = useState([])
  const [summary, setSummary] = useState(null)
  const [summaryNotice, setSummaryNotice] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reprocessing, setReprocessing] = useState(false)

  const load = useCallback(async () => {
    try {
      const current = await getMeeting(meetingId)
      setMeeting(current)
      setError(null)

      const transcript = await getTranscript(meetingId)
      setSegments(transcript.segments)

      try {
        setSummary(await getSummary(meetingId))
        setSummaryNotice(null)
      } catch (summaryError) {
        setSummary(null)
        setSummaryNotice(summaryError.message)
      }
    } catch (loadError) {
      setError(`Could not load this meeting: ${loadError.message}`)
    } finally {
      setLoading(false)
    }
  }, [meetingId])

  useEffect(() => {
    setLoading(true)
    load()
  }, [load])

  useEffect(() => {
    if (!meeting || !isProcessing(meeting.status)) return undefined
    const timer = setInterval(load, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [meeting, load])

  async function handleReprocess() {
    setReprocessing(true)
    try {
      await processMeeting(meetingId)
      await load()
    } catch (processError) {
      setError(processError.message)
    } finally {
      setReprocessing(false)
    }
  }

  if (loading) {
    return (
      <p className="muted">
        <span className="spinner" /> Loading meeting...
      </p>
    )
  }

  if (error && !meeting) {
    return (
      <div>
        <div className="alert error">{error}</div>
        <button onClick={onBack}>Back to all meetings</button>
      </div>
    )
  }

  const working = isProcessing(meeting.status)

  return (
    <div>
      <div className="card">
        <div className="row">
          <h2 style={{ flex: 1, margin: 0 }}>{meeting.title}</h2>
          <span className={badgeClass(meeting.status)}>
            {working && <span className="spinner" />} {meeting.status}
          </span>
        </div>

        <div className="small muted" style={{ marginTop: 6 }}>
          {new Date(meeting.created_at).toLocaleString()}
          {meeting.duration ? ` · ${Math.round(meeting.duration)}s of audio` : ''}
        </div>

        {meeting.description && <p style={{ marginBottom: 0 }}>{meeting.description}</p>}

        {error && <div className="alert error" style={{ marginTop: 12 }}>{error}</div>}

        {meeting.status === 'FAILED' && meeting.error_message && (
          <div className="alert error" style={{ marginTop: 12 }}>
            <strong>Processing failed.</strong> {meeting.error_message}
          </div>
        )}

        {working && (
          <div className="alert info" style={{ marginTop: 12 }}>
            <span className="spinner" /> Processing is running ({meeting.status.toLowerCase()}).
            This page refreshes automatically.
          </div>
        )}

        <div className="row" style={{ marginTop: 14 }}>
          <audio controls src={audioUrl(meeting.id)} style={{ maxWidth: '100%' }} />
        </div>

        {!working && (
          <div className="row" style={{ marginTop: 14 }}>
            <button onClick={handleReprocess} disabled={reprocessing}>
              {reprocessing ? <><span className="spinner" /> Starting...</> : 'Run processing again'}
            </button>
          </div>
        )}
      </div>

      <div className="card">
        <h2>AI summary</h2>
        <Summary summary={summary} error={summary ? null : summaryNotice} />
      </div>

      <div className="card">
        <h2>Ask about this meeting</h2>
        <Chat meetingId={meeting.id} enabled={meeting.status === 'COMPLETED'} />
      </div>

      <div className="card">
        <h2>Transcript</h2>
        <Transcript segments={segments} />
      </div>
    </div>
  )
}
