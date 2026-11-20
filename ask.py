import ollama, chromadb

col = chromadb.PersistentClient(path="chroma_db").get_collection("quake_docs")
MAX_DISTANCE = 0.6   # raise this if you get "could not find" too often

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
    print("Earthquake chatbot. Type 'exit' to stop.")
    while True:
        q = input("\nYou: ").strip()
        if q.lower() in ("exit", "quit", ""):
            break
        text, metas = answer(q)
        print("\nBot:", text)
        if metas:
            print("Sources:", ", ".join(sorted({m['source'] for m in metas})))