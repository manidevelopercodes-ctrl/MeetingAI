export function formatTime(seconds) {
  const total = Math.max(0, Math.floor(seconds || 0))
  const minutes = String(Math.floor(total / 60)).padStart(2, '0')
  return `${minutes}:${String(total % 60).padStart(2, '0')}`
}

export default function Transcript({ segments, loading }) {
  if (loading) {
    return (
      <p className="muted">
        <span className="spinner" /> Loading transcript...
      </p>
    )
  }

  if (!segments || segments.length === 0) {
    return <div className="empty small">No transcript yet.</div>
  }

  return (
    <div className="transcript">
      {segments.map((segment) => (
        <div className="segment" key={segment.id}>
          <span className="time">
            {formatTime(segment.start_time)} - {formatTime(segment.end_time)}
          </span>
          <span className="speaker">{segment.speaker}</span>
          <span>{segment.text}</span>
        </div>
      ))}
    </div>
  )
}
