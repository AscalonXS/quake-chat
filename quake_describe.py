"""
quake_describe.py - connect the impact calculator to Llama (Ollama) and RAG

    from quake_describe import explain_scenario
    out = explain_scenario(35.76, 129.19, 6.5, 10)
    print(out["description"])

Flow:  inputs -> get_impact (Python does every number) -> RAG guidance -> Llama writes the text
       -> number check -> (retry once) -> plain fallback text if the check still fails.

Command line:  python quake_describe.py 35.76 129.19 6.5 10
"""
import re
import sys

from impacts import get_impact

MODEL = "quake-bot"            # the model you built from your Modelfile
EMBED_MODEL = "bge-m3"
CHROMA_PATH = "chroma_db"
COLLECTION = "quake_docs"
MAX_DISTANCE = 0.6             # same idea as in ask.py: ignore document chunks that match badly
MAX_CHUNK_CHARS = 1200         # keeps the prompt inside num_ctx 4096

DISCLAIMER = (
    "DISCLAIMER: Earthquakes and aftershocks cannot be predicted. "
    "All shaking, impact, and aftershock figures above are hypothetical simulations and "
    "historical statistical estimates—not a prediction or an official warning. "
    "In an emergency, follow official instructions and call your local emergency number."
)

FORBIDDEN_WORDS = (
    "predict", "prediction", "predicting", "predicted",
    "will happen", "will strike", "will occur", "will hit",
    "is going to hit", "is going to strike", "guaranteed",
)

def forbidden_claims(text):
    low = text.lower()
    return [w for w in FORBIDDEN_WORDS if w in low]

PROMPT = """    You are an earthquake impact analyst writing for the public.
Write a clear, structured description of the scenario below in about 150 to 200 words using 3 short paragraphs and a bulleted action list.

Format:
- Paragraph 1 (Shaking & Cost): Describe what people would feel, who is affected, the cost range (say it is a rough estimate), the alert level, and mention once that the cost could be higher if shaking is stronger using the figure in RESULT.
- Paragraph 2 (Secondary Hazards & Confidence): Cover tsunami, landslide, and liquefaction risks, followed by the confidence level and main assumptions.
- Paragraph 3 (Guidance): Write "What to do:" on its own line, followed by 3 short bullet points (- ) taken from GUIDANCE. If GUIDANCE is empty, write "- Follow the instructions of your local authorities." instead.

Rules:
- Use ONLY the facts and numbers written in RESULT, ASSUMPTIONS and GUIDANCE. Copy numbers exactly as written.
- Do NOT calculate, convert, round, add or estimate any number.
- Separate each paragraph with a blank line.
- Never call this a prediction or a warning.
{extra}
RESULT:
{result_block}

ASSUMPTIONS:
{assumptions}

GUIDANCE:
{guidance}

"""

# ---------------------------------------------------------------- the model call (easy to replace in tests)
def call_llm(prompt):
    import ollama
    r = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.2, "num_predict": 450})
    return r["message"]["content"]

# ---------------------------------------------------------------- RAG guidance
def guidance_queries(result):
    q = ["what to do during a strong earthquake", "what to do after an earthquake"]
    env = result["environment"]
    if env["tsunami"]["level"] in ("possible", "possible if offshore"):
        q.append("tsunami warning what to do coastal evacuation")
    if env["landslide"]["level"] in ("possible", "moderate to high"):
        q.append("landslides after an earthquake safety")
    return q

def get_guidance(result, per_query=2, max_chunks=4):
    """Returns (guidance_text, source_names). Empty if the document database is not available."""
    try:
        import chromadb, ollama
        col = chromadb.PersistentClient(path=CHROMA_PATH).get_collection(COLLECTION)
        seen, chunks, sources = set(), [], []
        for q in guidance_queries(result):
            emb = ollama.embed(model=EMBED_MODEL, input=q)["embeddings"]
            res = col.query(query_embeddings=emb, n_results=per_query)
            for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
                if dist > MAX_DISTANCE or doc in seen:
                    continue
                seen.add(doc)
                chunks.append(f"[{meta.get('source', '?')}] {doc[:MAX_CHUNK_CHARS]}")
                sources.append(meta.get("source", "?"))
        chunks = chunks[:max_chunks]
        return "\n\n".join(chunks), sorted(set(sources))
    except Exception as e:
        print("WARNING: guidance not available:", e)
        return "", []

# ---------------------------------------------------------------- number check
_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")

def numbers_in(text):
    out = []
    for m in _NUM.findall(str(text)):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out

def allowed_numbers(result, guidance):
    allowed = set()
    for v in result["text"].values():
        allowed.update(numbers_in(v))
    allowed.update(numbers_in(" ".join(result["assumptions"])))
    for w in result["warnings"]:
        allowed.update(numbers_in(w))
    allowed.update(numbers_in(guidance))
    allowed.update({1.0, 2.0, 3.0})                      # numbering of the three actions
    return allowed

def _same(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))

def unknown_numbers(description, allowed):
    return sorted({n for n in numbers_in(description) if not any(_same(n, a) for a in allowed)})

def missing_cost_numbers(description, result):
    have = numbers_in(description)
    return sorted({n for n in numbers_in(result["text"]["cost_range"]) if not any(_same(n, h) for h in have)})

# ---------------------------------------------------------------- prompt and fallback text
def build_prompt(result, guidance, problems=None):
    result_block = "\n".join(f"- {k}: {v}" for k, v in result["text"].items())
    assumptions = "\n".join(f"- {a}" for a in result["assumptions"])
    extra = ""
    if problems:
        extra = "\nYour previous answer had problems. Fix them: " + " ".join(problems) + "\n"
    return PROMPT.format(extra=extra, result_block=result_block, assumptions=assumptions,
                         guidance=guidance if guidance else "(empty)")

def fallback_description(result):
    """Plain text built only from the result. Used when Llama keeps producing numbers that are not in the result."""
    t = result["text"]
    return (f"{t['scenario']} The strongest shaking would be {t['strongest_shaking']}. "
            f"{t['people_strong_shaking'][0].upper() + t['people_strong_shaking'][1:]}. Estimated cost: {t['cost_range']}. "
            f"Alert level: {t['alert_level']}. Tsunami: {t['tsunami']}. Landslide: {t['landslide']}. "
            f"Liquefaction: {t['liquefaction']}. Confidence: {t['confidence']}. "
            "What to do: follow the instructions of your local authorities.")

# ---------------------------------------------------------------- the whole pipeline
def describe(result, guidance="", retries=1):
    allowed = allowed_numbers(result, guidance)
    problems, history = [], []
    for attempt in range(retries + 1):
        text = call_llm(build_prompt(result, guidance, problems)).strip()
        bad = unknown_numbers(text, allowed)
        miss = missing_cost_numbers(text, result)
        history.append({"attempt": attempt + 1, "unknown_numbers": bad, "missing_cost_numbers": miss})
        if not bad and not miss:
            return text, False, history
        problems = []
        if bad:
            problems.append("These numbers are not in RESULT, ASSUMPTIONS or GUIDANCE, so do not use them: "
                            + ", ".join(f"{n:g}" for n in bad) + ".")
        if miss:
            problems.append("You left out or changed these cost numbers: " + ", ".join(f"{n:g}" for n in miss)
                            + ". Copy the cost range exactly.")
    return fallback_description(result), True, history

def explain_scenario(lat, lon, magnitude, depth_km, region_name=None, offshore=None, use_rag=True, retries=1):
    result = get_impact(lat, lon, magnitude, depth_km, region_name=region_name, offshore=offshore)
    guidance, sources = get_guidance(result) if use_rag else ("", [])
    text, used_fallback, history = describe(result, guidance, retries=retries)
    return {"description": text + "\n\n" + DISCLAIMER, "used_fallback": used_fallback, "checks": history,
            "guidance_sources": sources, "result": result}

if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit("usage: python quake_describe.py LAT LON MAGNITUDE DEPTH_KM")
    lat, lon, mag, dep = map(float, sys.argv[1:5])
    out = explain_scenario(lat, lon, mag, dep)
    print(out["description"])
    print("\nSources:", ", ".join(out["guidance_sources"]) or "none")
    print("Used the plain fallback text:", out["used_fallback"])
    print("Number checks:", out["checks"])