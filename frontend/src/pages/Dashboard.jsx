import { useCallback, useEffect, useState } from 'react'
import MeetingList from '../components/MeetingList.jsx'
import MeetingUpload from '../components/MeetingUpload.jsx'
import { deleteMeeting, isProcessing, listMeetings, searchTranscripts } from '../services/api.js'

const POLL_INTERVAL_MS = 4000

export default function Dashboard({ onOpenMeeting }) {
  const [meetings, setMeetings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showUpload, setShowUpload] = useState(false)

  const [query, setQuery] = useState('')
  const [hits, setHits] = useState(null)
  const [searching, setSearching] = useState(false)

  const refresh = useCallback(async () => {
    try {
      setMeetings(await listMeetings())
      setError(null)
    } catch (loadError) {
      setError(`Could not load meetings: ${loadError.message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Keep polling while anything is still being processed.
  useEffect(() => {
    if (!meetings.some((meeting) => isProcessing(meeting.status))) return undefined
    const timer = setInterval(refresh, POLL_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [meetings, refresh])

  async function handleDelete(meeting) {
    if (!window.confirm(`Delete "${meeting.title}"? This also removes its audio and transcript.`)) {
      return
    }
    try {
      await deleteMeeting(meeting.id)
      refresh()
    } catch (deleteError) {
      setError(`Could not delete the meeting: ${deleteError.message}`)
    }
  }

  async function handleSearch(event) {
    event.preventDefault()
    if (query.trim().length < 2) return
    setSearching(true)
    try {
      setHits((await searchTranscripts(query.trim())).hits)
      setError(null)
    } catch (searchError) {
      setError(`Search failed: ${searchError.message}`)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div>
      {showUpload ? (
        <MeetingUpload
          onCancel={() => setShowUpload(false)}
          onUploaded={() => {
            setShowUpload(false)
            refresh()
          }}
        />
      ) : (
        <div className="row" style={{ marginBottom: 16 }}>
          <button className="primary" onClick={() => setShowUpload(true)}>
            New meeting
          </button>
          <button onClick={refresh}>Refresh</button>
        </div>
      )}

      <div className="card">
        <h2>Search transcripts</h2>
        <form className="chat-form" onSubmit={handleSearch}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a topic across all meetings"
          />
          <button type="submit" disabled={searching || query.trim().length < 2}>
            {searching ? <span className="spinner" /> : 'Search'}
          </button>
          {hits !== null && (
            <button
              type="button"
              onClick={() => {
                setHits(null)
                setQuery('')
              }}
            >
              Clear
            </button>
          )}
        </form>

        {hits !== null && (
          hits.length === 0 ? (
            <p className="small muted" style={{ marginTop: 12 }}>
              No transcript matched that search.
            </p>
          ) : (
            <div style={{ marginTop: 12 }}>
              {hits.map((hit) => (
                <div className="segment" key={hit.segment_id}>
                  <span className="speaker">
                    <button className="title" onClick={() => onOpenMeeting(hit.meeting_id)}>
                      {hit.meeting_title}
                    </button>
                  </span>
                  <span>{hit.text}</span>
                </div>
              ))}
            </div>
          )
        )}
      </div>

      <div className="card">
        <h2>Meetings</h2>
        <MeetingList
          meetings={meetings}
          loading={loading}
          error={error}
          onOpen={onOpenMeeting}
          onDelete={handleDelete}
        />
      </div>
    </div>
  )
}
