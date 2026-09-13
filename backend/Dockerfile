# Optional container image for the backend. Local Windows development is the
# primary setup; see the README.
FROM python:3.12-slim

# ffmpeg is what faster-whisper uses to decode mp3/m4a/mp4/webm input.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
