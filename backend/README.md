# Backend

## Start
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then put the real key in .env
uvicorn main:app --reload --port 8000
```
Docs / quick test: http://localhost:8000/docs

## API contract (Day 1: approve with Vadim and Bobs)

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | none | `{status, model_backend}` |
| `POST /api/chat` | JSON `{question}` | `{answer, sources:[{title,page,snippet}], grounded}` |
| `POST /api/audio` | multipart `file` (max 25 MB) | `{transcript, answer, sources, grounded}` |
| `POST /api/image` | multipart `file` (jpeg/png/webp, max 5 MB) | `{description, answer, sources, grounded, note}` |
| `GET /api/earthquakes` | none | `{events:[{id,mag,place,depth_km,time,url}], updated_at, source, stale}` |
| `GET /api/alert` | none | `{summary, quake, severity, stale}` |

- `time` is Unix ms, `updated_at` is Unix seconds (null if the saved sample is used).
- `grounded=false` means the fallback fired: show "not found in the documents".
- Errors: JSON `{"detail": "friendly message"}` with status 400/413/415/422/503.

## Bobs's functions
Replace the fake bodies in `rag_interface.py`: `answer_question`, `transcribe_audio`,
`describe_photo`, `summarize_quake`. Signatures stay the same.

## Demo checklist (Day 7)
- Clean restart using the steps above
- If the feed is offline, `/api/earthquakes` returns the saved sample (`source: "sample"`)
- Record the backup video
