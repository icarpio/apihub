from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/polls", tags=["polls"])

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme123")

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
    cur  = conn.cursor()
    cur.execute("""
        CREATE SCHEMA IF NOT EXISTS fastapiprojects;

        CREATE TABLE IF NOT EXISTS fastapiprojects.polls (
            id         SERIAL PRIMARY KEY,
            question   TEXT        NOT NULL,
            active     BOOLEAN     NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS fastapiprojects.poll_options (
            id      SERIAL PRIMARY KEY,
            poll_id INTEGER NOT NULL REFERENCES fastapiprojects.polls(id) ON DELETE CASCADE,
            label   TEXT    NOT NULL,
            votes   INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    cur.close(); conn.close()

try:
    init_db()
except Exception as e:
    print(f"[polls] DB init warning: {e}")

# ── Models ────────────────────────────────────────────────

class PollOptionIn(BaseModel):
    label: str

class PollCreate(BaseModel):
    question: str
    options: List[str]   # min 2, max 8

class PollOption(BaseModel):
    id: int
    label: str
    votes: int
    percent: float

class Poll(BaseModel):
    id: int
    question: str
    active: bool
    created_at: datetime
    options: List[PollOption]
    total_votes: int

class VoteRequest(BaseModel):
    option_id: int

# ── Helpers ───────────────────────────────────────────────

def fetch_poll(poll_id: int, cur) -> dict:
    cur.execute("SELECT id, question, active, created_at FROM fastapiprojects.polls WHERE id = %s", (poll_id,))
    row = cur.fetchone()
    if not row:
        return None
    poll = dict(row)
    cur.execute("SELECT id, label, votes FROM fastapiprojects.poll_options WHERE poll_id = %s ORDER BY id", (poll_id,))
    options = [dict(r) for r in cur.fetchall()]
    total = sum(o["votes"] for o in options)
    for o in options:
        o["percent"] = round((o["votes"] / total * 100) if total > 0 else 0, 1)
    poll["options"]     = options
    poll["total_votes"] = total
    return poll

# ── Endpoints ─────────────────────────────────────────────

# GET all active polls
@router.get("", response_model=List[Poll])
async def list_polls():
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id FROM fastapiprojects.polls WHERE active = TRUE ORDER BY created_at DESC")
        ids  = [r["id"] for r in cur.fetchall()]
        polls = [fetch_poll(i, cur) for i in ids]
        cur.close(); conn.close()
        return polls
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# GET single poll
@router.get("/{poll_id}", response_model=Poll)
async def get_poll(poll_id: int):
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        poll = fetch_poll(poll_id, cur)
        cur.close(); conn.close()
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found.")
        return poll
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# POST create poll (admin only)
@router.post("", response_model=Poll, status_code=201)
async def create_poll(data: PollCreate, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token.")
    if len(data.options) < 2 or len(data.options) > 8:
        raise HTTPException(status_code=400, detail="Must provide 2–8 options.")
    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question is required.")
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "INSERT INTO fastapiprojects.polls (question) VALUES (%s) RETURNING id",
            (data.question.strip(),)
        )
        poll_id = cur.fetchone()["id"]
        for opt in data.options:
            cur.execute(
                "INSERT INTO fastapiprojects.poll_options (poll_id, label) VALUES (%s, %s)",
                (poll_id, opt.strip())
            )
        conn.commit()
        poll = fetch_poll(poll_id, cur)
        cur.close(); conn.close()
        return poll
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# POST vote
@router.post("/{poll_id}/vote", response_model=Poll)
async def vote(poll_id: int, data: VoteRequest):
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Check poll exists and is active
        cur.execute("SELECT active FROM fastapiprojects.polls WHERE id = %s", (poll_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Poll not found.")
        if not row["active"]:
            raise HTTPException(status_code=400, detail="This poll is closed.")
        # Check option belongs to poll
        cur.execute(
            "SELECT id FROM fastapiprojects.poll_options WHERE id = %s AND poll_id = %s",
            (data.option_id, poll_id)
        )
        if not cur.fetchone():
            raise HTTPException(status_code=400, detail="Invalid option for this poll.")
        # Increment vote
        cur.execute(
            "UPDATE fastapiprojects.poll_options SET votes = votes + 1 WHERE id = %s",
            (data.option_id,)
        )
        conn.commit()
        poll = fetch_poll(poll_id, cur)
        cur.close(); conn.close()
        return poll
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# DELETE close poll (admin only)
@router.delete("/{poll_id}")
async def close_poll(poll_id: int, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid admin token.")
    try:
        conn = get_conn()
        cur  = conn.cursor()
        cur.execute("UPDATE fastapiprojects.polls SET active = FALSE WHERE id = %s", (poll_id,))
        conn.commit()
        cur.close(); conn.close()
        return {"message": "Poll closed."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))