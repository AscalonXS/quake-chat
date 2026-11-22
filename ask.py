import json, re
import ollama, chromadb
from quake_describe import explain_scenario
from quake_simulate import simulate_area

col = chromadb.PersistentClient(path="chroma_db").get_collection("quake_docs")
MAX_DISTANCE = 0.6

SCENARIO_HINTS = ("what if", "scenario", "simulate", "simulation", "happening in", "hit ", "hits ", "magnitude", "m7", "m6", "m5")
SIM_DETAIL_HINTS = ("simulate", "simulation", "traffic", "road", "village", "mountain", "crowd", "human", "feel", "perceive", "where will", "time")

def parse_request(question):
    """Extract lat, lon, magnitude, depth_km, and optional hour (0-23) from user text."""
    extract_prompt = (
        "Extract earthquake parameters from the user's message as JSON ONLY.\n"
        "Keys: \"is_scenario\" (boolean), \"lat\" (float), \"lon\" (float), "
        "\"magnitude\" (float), \"depth_km\" (float, default 10.0 if omitted), "
        "\"hour\" (integer 0-23 if a time of day is mentioned like '8 AM'->8, '6 PM'->18, 'night'->23, otherwise null).\n"
        "If the user is asking a general safety question without a location/magnitude, return {\"is_scenario\": false}.\n"
        "Use accurate coordinates for any city, town, or mountain region mentioned.\n\n"
        f"Message: {question}"
    )
    r = ollama.chat(
        model="quake-bot",
        messages=[{"role": "user", "content": extract_prompt}],
        format="json",
        options={"temperature": 0.0},
    )
    try:
        data = json.loads(r["message"]["content"])
        if data.get("is_scenario") and all(k in data for k in ("lat", "lon", "magnitude")):
            hr = int(data["hour"]) if data.get("hour") is not None else None
            return (
                float(data["lat"]),
                float(data["lon"]),
                float(data["magnitude"]),
                float(data.get("depth_km") or 10.0),
                hr,
            )
    except Exception:
        pass
    return None

def answer(question):
    q_emb = ollama.embed(model="bge-m3", input=question)["embeddings"]
    res = col.query(query_embeddings=q_emb, n_results=4)
    docs, metas, dists = res["documents"][0], res["metadatas"][0], res["distances"][0]

    if not docs or dists[0] > MAX_DISTANCE:
        return ("I could not find this in my documents. Please check official sources. "
                "In an emergency, call your local emergency number."), []

    context = "\n\n".join(f"[{m['source']}] {d}" for d, m in zip(docs, metas))
    prompt = (
        "Answer using ONLY the context below. Give short steps and mention the source "
        "name in brackets. If the context does not answer the question, say you are not sure.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    r = ollama.chat(model="quake-bot", messages=[{"role": "user", "content": prompt}])
    return r["message"]["content"], metas

if __name__ == "__main__":
    print("Earthquake Assistant (RAG Q&A + Scenario + Area Simulation). Type 'exit' to stop.")
    while True:
        q = input("\nYou: ").strip()
        if q.lower() in ("exit", "quit", ""):
            break

        low = q.lower()
        if any(h in low for h in SCENARIO_HINTS) and re.search(r"\d+(\.\d+)?", low):
            params = parse_request(q)
            if params:
                lat, lon, mag, dep, hr = params
                if any(w in low for w in SIM_DETAIL_HINTS):
                    print(f"\n[Running detailed area & human perception simulation at lat={lat}, lon={lon}, M{mag}, hour={hr if hr is not None else 'now'}...]")
                    out = simulate_area(lat, lon, mag, dep, hour=hr)
                    print("\nBot:\n" + out["simulation"])
                else:
                    print(f"\n[Running macro scenario summary at lat={lat}, lon={lon}, M{mag}...]")
                    out = explain_scenario(lat, lon, mag, dep)
                    print("\nBot:\n" + out["description"])
                continue

        text, metas = answer(q)
        print("\nBot:", text)
        if metas:
            print("Sources:", ", ".join(sorted({m['source'] for m in metas})))