"""
Interface to Bobs's AI code. Replace the bodies with real calls
(or `from bobs_module import ...`). Signatures must stay the same.
Each function may raise TimeoutError / RuntimeError; main.py handles them.
"""

def answer_question(question: str) -> dict:
    """-> {"answer": str, "sources": [{"title","page","snippet"}], "grounded": bool}"""
    return {
        "answer": f"[FAKE] You asked: {question}",
        "sources": [{"title": "Fake source", "page": 1, "snippet": "Drop, cover and hold on."}],
        "grounded": True,
    }

def transcribe_audio(path: str) -> str:
    """Whisper: audio file path -> text."""
    return "[FAKE] what should I do during an earthquake"

def describe_photo(image_bytes: bytes, mime: str) -> str:
    """Hosted multimodal LLM: image -> two-sentence hazard description."""
    return "[FAKE] A tall bookshelf next to a bed. A crack runs along the wall."

def summarize_quake(quake: dict) -> str:
    """Quake dict -> two-sentence summary + one safety tip from documents."""
    return f"[FAKE] M{quake['mag']} earthquake near {quake['place']}. Tip: drop, cover and hold on."
