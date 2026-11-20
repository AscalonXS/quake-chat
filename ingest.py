import pathlib
import ollama, chromadb

client = chromadb.PersistentClient(path="chroma_db")
col = client.get_or_create_collection("quake_docs", metadata={"hnsw:space": "cosine"})

def chunk(text, size=300, overlap=50):
    words = text.split()
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step)]

for f in pathlib.Path("docs").glob("*.txt"):
    chunks = chunk(f.read_text(encoding="utf-8"))
    embs = ollama.embed(model="bge-m3", input=chunks)["embeddings"]
    col.upsert(
        ids=[f"{f.stem}-{i}" for i in range(len(chunks))],
        documents=chunks,
        embeddings=embs,
        metadatas=[{"source": f.stem} for _ in chunks],
    )

print("chunks stored:", col.count())