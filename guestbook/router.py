from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from datetime import datetime
import psycopg2
import psycopg2.extras
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/guestbook", tags=["guestbook"])

# ── DB connection ─────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
        options="-c search_path=fastapiprojects"
    )

# ── Create table if it doesn't exist ─────────────────────

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE SCHEMA IF NOT EXISTS fastapiprojects;
        CREATE TABLE IF NOT EXISTS fastapiprojects.guestbook (
            id         SERIAL PRIMARY KEY,
            name       VARCHAR(100) NOT NULL,
            city       VARCHAR(100) NOT NULL,
            comment    TEXT         NOT NULL,
            created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"[guestbook] DB init warning: {e}")

# ── Models ───────────────────────────────────────────────

class GuestEntry(BaseModel):
    name: str
    city: str
    comment: str

class GuestEntryResponse(BaseModel):
    id: int
    name: str
    city: str
    comment: str
    created_at: datetime

# ── Endpoints ────────────────────────────────────────────

@router.post("", response_model=GuestEntryResponse, status_code=201)
async def create_entry(entry: GuestEntry):
    name    = entry.name.strip()
    city    = entry.city.strip()
    comment = entry.comment.strip()
    if not name or not city or not comment:
        raise HTTPException(status_code=400, detail="All fields are required.")
    if len(comment) > 500:
        raise HTTPException(status_code=400, detail="Comment must be 500 characters or less.")
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """INSERT INTO fastapiprojects.guestbook (name, city, comment)
               VALUES (%s, %s, %s)
               RETURNING id, name, city, comment, created_at""",
            (name, city, comment)
        )
        row = cur.fetchone()
        conn.commit()
        cur.close(); conn.close()
        return dict(row)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("", response_model=List[GuestEntryResponse])
async def list_entries():
    try:
        conn = get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT id, name, city, comment, created_at
               FROM fastapiprojects.guestbook
               ORDER BY created_at DESC
               LIMIT 50"""
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")