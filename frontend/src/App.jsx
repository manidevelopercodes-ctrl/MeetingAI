import { useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import MeetingDetails from './pages/MeetingDetails.jsx'

// A single piece of state stands in for a router: this app has only two screens.
export default function App() {
  const [selectedId, setSelectedId] = useState(null)

  return (
    <>
      <header className="app-header">
        <h1>MeetingAI</h1>
        <span className="tagline">Local meeting transcription, summaries and chat</span>
        <span className="spacer" />
        {selectedId !== null && (
          <button onClick={() => setSelectedId(null)}>&larr; All meetings</button>
        )}
      </header>

      <main className="container">
        {selectedId === null ? (
          <Dashboard onOpenMeeting={setSelectedId} />
        ) : (
          <MeetingDetails meetingId={selectedId} onBack={() => setSelectedId(null)} />
        )}
      </main>
    </>
  )
}
