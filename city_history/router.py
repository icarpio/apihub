from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter(prefix="/api/city-history", tags=["city-history"])

# ── DB ────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        options="-c search_path=fastapiprojects"
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE SCHEMA IF NOT EXISTS fastapiprojects;
        CREATE TABLE IF NOT EXISTS fastapiprojects.city_history (
            id         SERIAL PRIMARY KEY,
            city_key   VARCHAR(150) UNIQUE NOT NULL,  -- lowercase normalized key for lookup
            city       VARCHAR(150) NOT NULL,          -- official name returned by OpenAI
            history    TEXT         NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"[city_history] DB init warning: {e}")

# ── Models ────────────────────────────────────────────────

class CityHistoryRequest(BaseModel):
    city: str  # Always returns English — frontend handles translation

class CityHistoryResponse(BaseModel):
    city: str
    text: str
    cached: bool = False  # True if served from DB, False if freshly generated

# ── Helpers ───────────────────────────────────────────────

def normalize(city: str) -> str:
    """Normalize city name to use as cache key."""
    return city.strip().lower()

def get_from_cache(city_key: str):
    """Return (city, history) from DB or None if not found."""
    try:
        conn = get_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT city, history FROM fastapiprojects.city_history WHERE city_key = %s",
            (city_key,)
        )
        row = cur.fetchone()
        cur.close(); conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[city_history] Cache read error: {e}")
        return None

def save_to_cache(city_key: str, city: str, history: str):
    """Insert into DB. If city_key already exists, do nothing (race condition safety)."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO fastapiprojects.city_history (city_key, city, history)
               VALUES (%s, %s, %s)
               ON CONFLICT (city_key) DO NOTHING""",
            (city_key, city, history)
        )
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"[city_history] Cache write error: {e}")

# ── Endpoint ──────────────────────────────────────────────

@router.post("", response_model=CityHistoryResponse)
async def get_city_history(request: CityHistoryRequest):
    city_input = request.city.strip()
    if not city_input:
        raise HTTPException(status_code=400, detail="City name is required.")

    city_key = normalize(city_input)

    # 1. Check cache first
    cached = get_from_cache(city_key)
    if cached:
        return CityHistoryResponse(
            city=cached["city"],
            text=cached["history"],
            cached=True
        )

    # 2. Not in cache — call OpenAI
    prompt = f"""
Write a concise historical summary of the city "{city_input}" in exactly 200 words.
Focus on its founding, key historical events, cultural significance, and modern relevance.
Write in clear, engaging English — no bullet points, continuous prose.

Return ONLY valid JSON with exactly these two fields:
{{
  "city": "Official city name",
  "text": "The 200-word historical summary here."
}}

Return ONLY the JSON object, no markdown, no extra text.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a historian that returns only valid JSON in English."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        if "city" not in data or "text" not in data:
            raise ValueError("Missing fields in response")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating history: {str(e)}")

    # 3. Save to cache for future requests
    save_to_cache(city_key, data["city"], data["text"])

    return CityHistoryResponse(
        city=data["city"],
        text=data["text"],
        cached=False
    )