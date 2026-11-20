import os, tempfile
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import rag_interface as rag
import usgs

app = FastAPI(title="Earthquake Preparedness Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

MAX_IMAGE = int(os.getenv("MAX_IMAGE_MB", "5")) * 1024 * 1024
MAX_AUDIO = int(os.getenv("MAX_AUDIO_MB", "25")) * 1024 * 1024
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
EMERGENCY = "Emergency: 119 (Korea fire/rescue), 112 (police), 911 (US)."

FRIENDLY = {
    "timeout": "The assistant is taking too long. Please try again in a moment.",
    "error": "Something went wrong on our side. Please try again.",
}

class ChatIn(BaseModel):
    question: str

def safe_ai(fn, *args):
    """Run an AI function; turn failures into a friendly 503 instead of a crash."""
    try:
        return fn(*args)
    except TimeoutError:
        raise HTTPException(503, FRIENDLY["timeout"])
    except Exception as e:
        print("AI error:", repr(e))
        raise HTTPException(503, FRIENDLY["error"])

def read_limited(file: UploadFile, limit: int) -> bytes:
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File too large (max {limit // 1024 // 1024} MB).")
    if not data:
        raise HTTPException(400, "Empty file.")
    return data

def result(r: dict) -> dict:
    return {"answer": r["answer"], "sources": r.get("sources", []),
            "grounded": bool(r.get("grounded"))}

@app.get("/health")
def health():
    return {"status": "ok", "model_backend": os.getenv("MODEL_BACKEND", "hosted")}

@app.post("/api/chat")
def chat(body: ChatIn):
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "Question is empty.")
    if len(q) > 1000:
        raise HTTPException(400, "Question is too long (max 1000 characters).")
    return result(safe_ai(rag.answer_question, q))

@app.post("/api/audio")
def audio(file: UploadFile = File(...)):
    data = read_limited(file, MAX_AUDIO)
    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        path = tmp.name
    try:
        text = safe_ai(rag.transcribe_audio, path).strip()
    finally:
        os.remove(path)
    if not text:
        raise HTTPException(422, "Could not understand the audio. Please try again.")
    return {"transcript": text, **result(safe_ai(rag.answer_question, text))}

@app.post("/api/image")
def image(file: UploadFile = File(...)):
    if file.content_type not in IMAGE_TYPES:
        raise HTTPException(415, "Only JPEG, PNG or WebP images are allowed.")
    data = read_limited(file, MAX_IMAGE)
    description = safe_ai(rag.describe_photo, data, file.content_type)
    return {"description": description, **result(safe_ai(rag.answer_question, description)),
            "note": "General safety advice, not a building inspection."}

@app.get("/api/earthquakes")
def earthquakes():
    return usgs.get_earthquakes()

_alert_cache: dict = {}

@app.get("/api/alert")
def alert():
    feed = usgs.get_earthquakes()
    quake = feed["events"][0]
    if quake["id"] not in _alert_cache:  # avoid calling the LLM on every refresh
        _alert_cache.clear()
        _alert_cache[quake["id"]] = safe_ai(rag.summarize_quake, quake)
    return {"summary": _alert_cache[quake["id"]], "quake": quake,
            "severity": "high" if quake["mag"] >= 5 else "normal",
            "stale": feed["stale"]}
