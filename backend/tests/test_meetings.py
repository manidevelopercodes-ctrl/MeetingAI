from pathlib import Path

from app.models.meeting import Meeting, MeetingStatus, TranscriptSegment
from tests.conftest import upload_meeting


# -- creation -----------------------------------------------------------


def test_upload_creates_meeting_in_uploaded_status(client, wav_bytes, settings):
    response = upload_meeting(client, wav_bytes)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Sprint planning"
    assert body["description"] == "Weekly planning session"
    assert body["status"] == MeetingStatus.UPLOADED.value
    assert Path(body["audio_path"]).exists()


def test_upload_stores_audio_under_the_configured_directory(client, wav_bytes, settings):
    body = upload_meeting(client, wav_bytes).json()

    assert Path(body["audio_path"]).parent == settings.audio_dir


def test_upload_rejects_unsupported_extension(client, wav_bytes):
    response = upload_meeting(client, wav_bytes, filename="notes.txt")

    assert response.status_code == 400
    assert "Unsupported audio format" in response.json()["detail"]


def test_upload_rejects_empty_file(client):
    response = upload_meeting(client, b"", filename="meeting.mp3")

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_upload_rejects_file_over_the_size_limit(client, settings):
    oversized = b"\x00" * (settings.max_upload_size_bytes + 1)

    response = upload_meeting(client, oversized, filename="meeting.mp3")

    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"]


def test_upload_accepts_every_documented_format(client, wav_bytes):
    for extension in ("mp3", "wav", "m4a", "mp4", "webm"):
        response = upload_meeting(client, wav_bytes, filename=f"meeting.{extension}")
        assert response.status_code == 201, extension


# -- listing and retrieval ---------------------------------------------


def test_list_is_empty_before_any_upload(client):
    response = client.get("/api/meetings")

    assert response.status_code == 200
    assert response.json() == []


def test_list_returns_newest_first(client, wav_bytes):
    upload_meeting(client, wav_bytes, title="First")
    upload_meeting(client, wav_bytes, title="Second")

    titles = [meeting["title"] for meeting in client.get("/api/meetings").json()]

    assert titles == ["Second", "First"]


def test_get_meeting_returns_the_meeting(client, wav_bytes):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]

    response = client.get(f"/api/meetings/{meeting_id}")

    assert response.status_code == 200
    assert response.json()["id"] == meeting_id


def test_get_unknown_meeting_returns_404(client):
    response = client.get("/api/meetings/4242")

    assert response.status_code == 404
    assert "4242" in response.json()["detail"]


# -- deletion -----------------------------------------------------------


def test_delete_removes_meeting_audio_and_vectors(client, wav_bytes, fake_embeddings):
    body = upload_meeting(client, wav_bytes).json()
    audio_path = Path(body["audio_path"])

    response = client.delete(f"/api/meetings/{body['id']}")

    assert response.status_code == 204
    assert not audio_path.exists()
    assert fake_embeddings.deleted == [body["id"]]
    assert client.get(f"/api/meetings/{body['id']}").status_code == 404


def test_delete_unknown_meeting_returns_404(client):
    assert client.delete("/api/meetings/4242").status_code == 404


# -- transcript and summary --------------------------------------------


def test_transcript_is_empty_before_processing(client, wav_bytes):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]

    body = client.get(f"/api/meetings/{meeting_id}/transcript").json()

    assert body["segments"] == []
    assert body["status"] == MeetingStatus.UPLOADED.value


def test_summary_returns_404_before_processing(client, wav_bytes):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]

    response = client.get(f"/api/meetings/{meeting_id}/summary")

    assert response.status_code == 404
    assert "no summary yet" in response.json()["detail"]


# -- search -------------------------------------------------------------


def test_search_finds_matching_transcript_segment(client, wav_bytes, db_session):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]
    db_session.add(
        TranscriptSegment(
            meeting_id=meeting_id,
            speaker="Speaker 1",
            start_time=0.0,
            end_time=4.0,
            text="We agreed to ship the billing migration on Friday.",
        )
    )
    db_session.commit()

    body = client.get("/api/meetings/search", params={"q": "billing"}).json()

    assert len(body["hits"]) == 1
    assert body["hits"][0]["meeting_id"] == meeting_id
    assert "billing migration" in body["hits"][0]["text"]


def test_search_is_case_insensitive(client, wav_bytes, db_session):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]
    db_session.add(
        TranscriptSegment(
            meeting_id=meeting_id, speaker="Speaker 1", start_time=0.0, end_time=1.0,
            text="Kubernetes rollout",
        )
    )
    db_session.commit()

    assert len(client.get("/api/meetings/search", params={"q": "KUBERNETES"}).json()["hits"]) == 1


def test_search_with_no_matches_returns_empty_list(client):
    body = client.get("/api/meetings/search", params={"q": "nothing here"}).json()

    assert body["hits"] == []


# -- processing guards --------------------------------------------------


def test_process_rejects_a_meeting_whose_audio_is_missing(client, wav_bytes):
    body = upload_meeting(client, wav_bytes).json()
    Path(body["audio_path"]).unlink()

    response = client.post(f"/api/meetings/{body['id']}/process")

    assert response.status_code == 400
    assert "missing" in response.json()["detail"]


def test_process_rejects_a_meeting_already_in_progress(client, wav_bytes, db_session):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]
    db_session.get(Meeting, meeting_id).status = MeetingStatus.SUMMARIZING
    db_session.commit()

    response = client.post(f"/api/meetings/{meeting_id}/process")

    assert response.status_code == 409
    assert "already being processed" in response.json()["detail"]


def test_chat_is_rejected_until_processing_completes(client, wav_bytes):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]

    response = client.post(
        f"/api/meetings/{meeting_id}/chat", json={"question": "What was decided?"}
    )

    assert response.status_code == 409
    assert "not ready for questions" in response.json()["detail"]


# -- database behaviour -------------------------------------------------


def test_deleting_a_meeting_cascades_to_its_segments(client, wav_bytes, db_session):
    meeting_id = upload_meeting(client, wav_bytes).json()["id"]
    db_session.add(
        TranscriptSegment(
            meeting_id=meeting_id, speaker="Speaker 1", start_time=0.0, end_time=1.0, text="Hello"
        )
    )
    db_session.commit()

    client.delete(f"/api/meetings/{meeting_id}")

    remaining = (
        db_session.query(TranscriptSegment)
        .filter(TranscriptSegment.meeting_id == meeting_id)
        .count()
    )
    assert remaining == 0


def test_meeting_status_enum_covers_the_documented_lifecycle():
    assert [status.value for status in MeetingStatus] == [
        "UPLOADED",
        "TRANSCRIBING",
        "SUMMARIZING",
        "INDEXING",
        "COMPLETED",
        "FAILED",
    ]
