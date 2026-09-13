def test_health_reports_healthy(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["app"] == "MeetingAI"


def test_health_reports_configured_models(client):
    body = client.get("/health").json()

    assert body["whisper_model"] == "small"
    assert body["ollama_model"] == "llama3.2"
    assert body["embedding_model"] == "all-MiniLM-L6-v2"
