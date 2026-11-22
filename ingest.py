"""
ingest.py - put the .txt documents from docs/ into the Chroma database (safer version)

Changes from the first version, to survive the Ollama error
    Post "http://127.0.0.1:xxxxx/tokenize": ... connection refused
 - sends the chunks to Ollama in small batches (16), not a whole file at once
 - if a batch fails, it splits the batch in two to find the bad chunk, retries, and skips only that chunk
 - first checks that the embedding model works at all, and prints what to do if it does not
 - resumes: chunks already in the database are skipped, so you can run it again after a crash
 - writes skipped chunks to data/ingest_skipped.txt

Run:  python ingest.py            (add --fresh to delete the database and start over)
"""
import pathlib, shutil, sys, time
import chromadb
import ollama

EMBED_MODEL = "bge-m3"        # if this keeps failing, try "nomic-embed-text" (run: ollama pull nomic-embed-text)
CHROMA_PATH = "chroma_db"
COLLECTION = "quake_docs"
BATCH = 16
CHUNK_WORDS, OVERLAP = 250, 40
MAX_CHARS = 1500              # a chunk longer than this is cut, very long chunks can crash the embedding runner

def chunk(text, size=CHUNK_WORDS, overlap=OVERLAP):
    words = text.split()
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step) if words[i:i + size]]

def embed_once(texts):
    return ollama.embed(model=EMBED_MODEL, input=texts)["embeddings"]

def embed_safe(texts, depth=0):
    """Returns a list with one embedding per text, or None for a text that could not be embedded."""
    try:
        return embed_once(texts)
    except Exception as e:
        if len(texts) > 1:                                  # split the batch to isolate the problem
            mid = len(texts) // 2
            return embed_safe(texts[:mid], depth + 1) + embed_safe(texts[mid:], depth + 1)
        for attempt in range(2):                            # a single chunk: wait, retry, then try a shorter version
            time.sleep(3)
            try:
                return embed_once([texts[0][: MAX_CHARS // (attempt + 1)]])
            except Exception as e2:
                e = e2
        print("   skipped one chunk:", str(e)[:120])
        return [None]

def check_model():
    try:
        v = embed_once(["earthquake safety test"])[0]
        print(f"embedding model '{EMBED_MODEL}' works (vector length {len(v)})")
    except Exception as e:
        print(f"\nThe embedding model '{EMBED_MODEL}' failed on a one-sentence test:\n  {str(e)[:300]}\n")
        print("This is a problem with Ollama itself, not with your documents. Try, in this order:")
        print("  1. Quit Ollama completely (system tray icon -> Quit), start it again, run this script again.")
        print("  2. In a terminal run:  ollama stop llama3.1:8b   and   ollama stop quake-bot   (frees memory)")
        print("  3. Update Ollama from ollama.com/download, then run:  ollama pull " + EMBED_MODEL)
        print("  4. Read the log:  %LOCALAPPDATA%\\Ollama\\server.log  (last 40 lines show why the runner crashed)")
        print("  5. Switch EMBED_MODEL to 'nomic-embed-text' above (also change it in ask.py and quake_describe.py)")
        sys.exit(1)

def main():
    if "--fresh" in sys.argv and pathlib.Path(CHROMA_PATH).exists():
        shutil.rmtree(CHROMA_PATH)
        print("deleted old database")
    check_model()

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    try:
        existing = set(col.get(include=[])["ids"])
    except Exception:
        existing = set()
    print("already in the database:", len(existing), "chunks")

    files = sorted(pathlib.Path("docs").glob("*.txt"))
    print("files found:", len(files))
    skipped = []
    for f in files:
        chunks = [c[:MAX_CHARS] for c in chunk(f.read_text(encoding="utf-8", errors="replace"))]
        items = [(f"{f.stem}-{i}", c) for i, c in enumerate(chunks) if f"{f.stem}-{i}" not in existing]
        print(f"{f.name}: {len(chunks)} chunks, {len(items)} new")
        for s in range(0, len(items), BATCH):
            part = items[s:s + BATCH]
            embs = embed_safe([t for _, t in part])
            ok = [(i, t, e) for (i, t), e in zip(part, embs) if e is not None]
            skipped += [i for (i, _), e in zip(part, embs) if e is None]
            if ok:
                col.upsert(ids=[i for i, _, _ in ok], documents=[t for _, t, _ in ok],
                           embeddings=[e for _, _, e in ok], metadatas=[{"source": f.stem} for _ in ok])
            print(f"   {min(s + BATCH, len(items))}/{len(items)}", end="\r")
        print()

    print("\ntotal chunks stored:", col.count())
    if skipped:
        pathlib.Path("data").mkdir(exist_ok=True)
        pathlib.Path("data/ingest_skipped.txt").write_text("\n".join(skipped), encoding="utf-8")
        print(f"skipped {len(skipped)} chunks (listed in data/ingest_skipped.txt). Run the script again to retry them.")

if __name__ == "__main__":
    main()