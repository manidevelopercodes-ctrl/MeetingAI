import { isProcessing } from '../services/api.js'

function badgeClass(status) {
  if (status === 'COMPLETED') return 'badge completed'
  if (status === 'FAILED') return 'badge failed'
  if (isProcessing(status)) return 'badge working'
  return 'badge uploaded'
}

function formatDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString()
}

export default function MeetingList({ meetings, loading, error, onOpen, onDelete }) {
  if (loading) {
    return (
      <p className="muted">
        <span className="spinner" /> Loading meetings...
      </p>
    )
  }

  if (error) {
    return <div className="alert error">{error}</div>
  }

  if (meetings.length === 0) {
    return (
      <div className="empty">
        <p>No meetings yet.</p>
        <p className="small">Upload a recording above to get started.</p>
      </div>
    )
  }

  return (
    <ul className="meeting-list">
      {meetings.map((meeting) => (
        <li key={meeting.id} className="meeting-item">
          <div className="meta">
            <button className="title" onClick={() => onOpen(meeting.id)}>
              {meeting.title}
            </button>
            <div className="small muted">{formatDate(meeting.created_at)}</div>
          </div>

          <span className={badgeClass(meeting.status)}>
            {isProcessing(meeting.status) && <span className="spinner" />} {meeting.status}
          </span>

          <button onClick={() => onOpen(meeting.id)}>Open</button>
          <button className="danger" onClick={() => onDelete(meeting)}>
            Delete
          </button>
        </li>
      ))}
    </ul>
  )
}
