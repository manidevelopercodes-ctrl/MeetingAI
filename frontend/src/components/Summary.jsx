function List({ items, emptyText }) {
  if (!items || items.length === 0) {
    return <p className="small muted">{emptyText}</p>
  }
  return (
    <ul className="clean">
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  )
}

export default function Summary({ summary, loading, error }) {
  if (loading) {
    return (
      <p className="muted">
        <span className="spinner" /> Generating summary view...
      </p>
    )
  }

  if (error) {
    return <div className="alert info">{error}</div>
  }

  if (!summary) {
    return <div className="empty small">No summary yet.</div>
  }

  const actionItems = summary.action_items || []

  return (
    <div>
      <p className="summary-text">{summary.summary || 'No summary text was produced.'}</p>

      <h3>Key points</h3>
      <List items={summary.key_points} emptyText="No key points were identified." />

      <h3>Decisions</h3>
      <List items={summary.decisions} emptyText="No decisions were identified." />

      <h3>Action items</h3>
      {actionItems.length === 0 ? (
        <p className="small muted">No action items were identified.</p>
      ) : (
        <table className="action-items">
          <thead>
            <tr>
              <th>Task</th>
              <th>Owner</th>
              <th>Due date</th>
            </tr>
          </thead>
          <tbody>
            {actionItems.map((item, index) => (
              <tr key={index}>
                <td>{item.task}</td>
                <td>{item.owner || <span className="muted">Unassigned</span>}</td>
                <td>{item.due_date || <span className="muted">Not set</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
