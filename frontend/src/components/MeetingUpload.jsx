import { useState } from 'react'
import { processMeeting, uploadMeeting } from '../services/api.js'

const ACCEPTED = '.mp3,.wav,.m4a,.mp4,.webm'

export default function MeetingUpload({ onUploaded, onCancel }) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setNotice(null)

    if (!title.trim()) return setError('Please give the meeting a title.')
    if (!file) return setError('Please choose an audio file.')

    setBusy(true)
    try {
      const meeting = await uploadMeeting({ title: title.trim(), description, file })
      setNotice('Uploaded. Starting transcription...')

      // Processing is best-effort: the upload already succeeded either way.
      try {
        await processMeeting(meeting.id)
      } catch (processError) {
        setNotice(`Uploaded, but processing could not start: ${processError.message}`)
      }

      setTitle('')
      setDescription('')
      setFile(null)
      event.target.reset()
      onUploaded(meeting)
    } catch (uploadError) {
      setError(uploadError.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <h2>New meeting</h2>

      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert info">{notice}</div>}

      <div className="field">
        <label htmlFor="title">Title</label>
        <input
          id="title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Sprint planning"
          disabled={busy}
        />
      </div>

      <div className="field">
        <label htmlFor="description">Description (optional)</label>
        <input
          id="description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Weekly planning session with the platform team"
          disabled={busy}
        />
      </div>

      <div className="field">
        <label htmlFor="file">Audio file</label>
        <input
          id="file"
          type="file"
          accept={ACCEPTED}
          onChange={(event) => setFile(event.target.files[0] ?? null)}
          disabled={busy}
        />
        <div className="small muted">Accepted formats: mp3, wav, m4a, mp4, webm.</div>
      </div>

      <div className="row">
        <button type="submit" className="primary" disabled={busy}>
          {busy ? <><span className="spinner" /> Uploading...</> : 'Upload and process'}
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  )
}
