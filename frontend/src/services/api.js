// Every backend call lives here so components never build URLs themselves.

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options)

  if (response.status === 204) return null

  let body = null
  const text = await response.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = text
    }
  }

  if (!response.ok) {
    const detail =
      (body && body.detail) || (typeof body === 'string' && body) || response.statusText
    throw new Error(detail || `Request failed with status ${response.status}`)
  }
  return body
}

export const getHealth = () => request('/health')

export const listMeetings = () => request('/api/meetings')

export const getMeeting = (id) => request(`/api/meetings/${id}`)

export const getTranscript = (id) => request(`/api/meetings/${id}/transcript`)

export const getSummary = (id) => request(`/api/meetings/${id}/summary`)

export const deleteMeeting = (id) => request(`/api/meetings/${id}`, { method: 'DELETE' })

export const processMeeting = (id) => request(`/api/meetings/${id}/process`, { method: 'POST' })

export const searchTranscripts = (query) =>
  request(`/api/meetings/search?q=${encodeURIComponent(query)}`)

export const askQuestion = (id, question) =>
  request(`/api/meetings/${id}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })

export function uploadMeeting({ title, description, file }) {
  const form = new FormData()
  form.append('title', title)
  if (description) form.append('description', description)
  form.append('file', file)
  return request('/api/meetings', { method: 'POST', body: form })
}

export const audioUrl = (id) => `${BASE}/api/meetings/${id}/audio`

// Statuses in which the backend is still working on the meeting.
export const IN_PROGRESS = ['TRANSCRIBING', 'SUMMARIZING', 'INDEXING']

export const isProcessing = (status) => IN_PROGRESS.includes(status)
