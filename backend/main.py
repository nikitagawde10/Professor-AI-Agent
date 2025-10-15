import os
import pathlib
import re
import textwrap
import time
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ============================================================
# CONFIGURATION
# ============================================================

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("MODEL_NAME", "mistral")
TOPIC_NAME = os.getenv("TOPIC_NAME", "Spanish Tutor (Beginner, English)")

# Load teaching notes from file or fallback text
def load_notes() -> str:
    env_notes = os.getenv("TOPIC_NOTES")
    if env_notes:
        return env_notes

    notes_file = pathlib.Path(__file__).with_name("notes_sp_en.md")
    if notes_file.exists():
        return notes_file.read_text(encoding="utf-8")

    # Fallback minimal prompt if file missing
    return textwrap.dedent("""
    AUDIENCE: Native English speakers (A1–A2). Reply in ENGLISH only.
    STYLE: concise, step-by-step; include pronunciation; end with "Try it:".
    WORD LOOKUPS: meaning + POS; pronunciation; morphology; etymology; collocations; 2–3 examples.
    PRONUNCIATION: explain mouth/tongue, minimal pairs, examples, mnemonic.
    GRAMMAR: subject pronouns order; tiny conj table if relevant; note irregulars.
    OUT OF SCOPE: reply exactly "This is outside my current topic."
    """)

TOPIC_NOTES = load_notes()

SYSTEM_PROMPT = f"""You are {TOPIC_NAME}.
Teach Spanish to a beginner, but EXPLAIN EVERYTHING IN ENGLISH.
Follow the didactic NOTES below strictly.

=== TEACHING NOTES ===
{TOPIC_NOTES}
=== END NOTES ===
"""

# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(title="Spanish Professor API")

# CORS (adjust for your frontend origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with ["http://localhost:5173"] for tighter security
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MODELS
# ============================================================

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str

# ============================================================
# GLOBAL HTTP CLIENT + WARMUP
# ============================================================

client: httpx.AsyncClient | None = None

@app.on_event("startup")
async def startup_event():
    """Initialize persistent HTTP client and warm up the model."""
    global client
    client = httpx.AsyncClient(timeout=60)

    # Warmup request to load model in memory
    print("🔥 Warming up model...")
    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": "warm up"}],
            "options": {"num_predict": 5},
            "stream": False,
        }
        await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        print(f"✅ Model '{MODEL_NAME}' warmed up successfully.")
    except Exception as e:
        print(f"⚠️ Warmup failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Close persistent client."""
    global client
    if client:
        await client.aclose()
        client = None
        print("🧹 HTTP client closed.")

# ============================================================
# HELPER: AUTO-ENHANCE USER QUERIES
# ============================================================

def augment_question(q: str) -> str:
    """
    If user typed a single word, add an instruction for full analysis.
    Handles Ñ pronunciation shortcut too.
    """
    qs = q.strip()
    word_like = re.fullmatch(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+(?:-[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+)?", qs)
    if word_like:
        return f"[WORD LOOKUP] Define and analyze the Spanish word: {qs}"
    if "pronounce" in qs.lower() and ("ñ" in qs.lower() or "ene" in qs.lower()):
        return "[PRONUNCIATION] Explain how to pronounce the letter Ñ with examples and a mnemonic."
    return qs

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
async def health():
    return {"ok": True, "model": MODEL_NAME}

@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    """Main endpoint: send user query to Ollama model."""
    global client
    if not client:
        raise HTTPException(status_code=500, detail="HTTP client not initialized.")

    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail='Missing "question".')

    q = augment_question(q)

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": q},
        ],
        "options": {
            "temperature": 0.3,
            "num_predict": 200,   # cap generation length for faster responses
        },
        "stream": False,
    }

    start = time.perf_counter()
    try:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Ollama error: {r.text}")
        data = r.json()
        answer = (data.get("message") or {}).get("content", "")
        elapsed = time.perf_counter() - start
        print(f"⏱️ Response time: {elapsed:.2f}s for query → {q[:40]}...")
        return AskResponse(answer=answer)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Cannot reach Ollama at {OLLAMA_URL}: {e}") from e