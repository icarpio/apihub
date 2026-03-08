from fastapi import APIRouter, HTTPException, Query
import httpx, asyncio, os, json
from datetime import date
from urllib.parse import urlparse
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()
router = APIRouter(prefix="/api/news", tags=["news"])

WORLD_NEWS_KEY = os.getenv("WORLD_NEWS_API_KEY", "")
BASE_URL = "https://api.worldnewsapi.com/top-news"

BLOCKED_IMAGE_DOMAINS = {"s3.elespanol.com"}
SKIP_KEYWORDS = {"horóscopo", "horoscopo", "horoscope", "tarot", "predicción", "prediccion", "portada"}

def get_conn():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    conn.cursor().execute("SET search_path TO fastapiprojects")
    return conn

def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fastapiprojects.news_cache (
                    id           SERIAL PRIMARY KEY,
                    cache_date   DATE NOT NULL,
                    country      VARCHAR(5) NOT NULL,
                    language     VARCHAR(5) NOT NULL,
                    articles     JSONB NOT NULL,
                    updates_today INT NOT NULL DEFAULT 1,
                    last_updated  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (cache_date, country, language)
                )
            """)
        conn.commit()

MAX_UPDATES_PER_DAY = 6
UPDATE_INTERVAL_HOURS = 24 // MAX_UPDATES_PER_DAY  # 4 horas

init_db()

def cache_get(country: str, language: str) -> dict | None:
    """Get most recent cached entry with metadata."""
    try:
        with get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT articles, updates_today, last_updated FROM fastapiprojects.news_cache WHERE country = %s AND language = %s ORDER BY cache_date DESC LIMIT 1",
                    (country, language)
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "articles":      row["articles"],
                    "updates_today": row["updates_today"],
                    "last_updated":  row["last_updated"],
                }
    except Exception as e:
        print(f"[news_cache] DB read error: {e}")
        return None

def should_refresh(cached: dict) -> bool:
    """Returns True if enough time has passed and we haven't hit the daily limit."""
    from datetime import datetime, timezone, timedelta
    if cached["updates_today"] >= MAX_UPDATES_PER_DAY:
        return False
    elapsed = datetime.now(timezone.utc) - cached["last_updated"].replace(tzinfo=timezone.utc)
    return elapsed >= timedelta(hours=UPDATE_INTERVAL_HOURS)

def cache_set(country: str, language: str, articles: list):
    today = date.today()
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM fastapiprojects.news_cache WHERE country = %s AND language = %s AND cache_date < %s",
                    (country, language, today)
                )
                cur.execute("""
                    INSERT INTO fastapiprojects.news_cache (cache_date, country, language, articles, updates_today, last_updated)
                    VALUES (%s, %s, %s, %s, 1, NOW())
                    ON CONFLICT (cache_date, country, language)
                    DO UPDATE SET
                        articles      = EXCLUDED.articles,
                        updates_today = fastapiprojects.news_cache.updates_today + 1,
                        last_updated  = NOW()
                """, (today, country, language, json.dumps(articles, ensure_ascii=False)))
            conn.commit()
    except Exception as e:
        print(f"[news_cache] DB write error: {e}")

def is_valid_title(title: str) -> bool:
    t = title.lower()
    return not any(kw in t for kw in SKIP_KEYWORDS)

async def image_ok(url: str) -> bool:
    if urlparse(url).netloc in BLOCKED_IMAGE_DOMAINS:
        return False
    try:
        async with httpx.AsyncClient(timeout=4, follow_redirects=True) as client:
            r = await client.head(url, headers={"User-Agent": "Mozilla/5.0"})
            return r.status_code == 200
    except Exception:
        return False

@router.get("")
async def get_news(
    country: str = Query("es"),
    language: str = Query("es"),
    headlines_only: bool = Query(False),
):
    if not WORLD_NEWS_KEY:
        raise HTTPException(status_code=500, detail="WORLD_NEWS_API_KEY not set.")

    cached = cache_get(country, language)

    # Serve from cache if it exists and it's not time to refresh yet
    if cached and not should_refresh(cached):
        return {"articles": cached["articles"], "total": len(cached["articles"]), "cached": True}

    params = {
        "source-country": country,
        "language":       language,
        "headlines-only": str(headlines_only).lower(),
        "api-key":        WORLD_NEWS_KEY,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(BASE_URL, params=params)

        # API limit reached or error → fall back to DB
        if r.status_code != 200:
            if cached:
                return {"articles": cached["articles"], "total": len(cached["articles"]), "cached": True}
            raise HTTPException(status_code=r.status_code, detail=r.text)

        # API responded OK — process articles
        clusters = r.json().get("top_news", [])
        seen_urls   = set()
        seen_titles = set()
        candidates  = []

        def extract_item(item):
            url       = (item.get("url") or "").strip()
            title     = (item.get("title") or "").strip()
            title_key = "".join(c for c in title.lower() if c.isalnum() or c == " ").strip()
            if not is_valid_title(title):
                return None
            if (url and url in seen_urls) or (title_key and title_key in seen_titles):
                return None
            if url:       seen_urls.add(url)
            if title_key: seen_titles.add(title_key)
            raw_image = item.get("image") or ""
            if not raw_image.startswith("http"):
                return None
            return {
                "title":        title,
                "summary":      (item.get("text") or "")[:300],
                "url":          url,
                "image":        raw_image,
                "source":       (item.get("source_country") or country).upper(),
                "published_at": item.get("publish_date") or "",
                "sentiment":    item.get("sentiment"),
            }

        # Pass 1: first item per cluster
        for cluster in clusters:
            news = cluster.get("news", [])
            if news:
                article = extract_item(news[0])
                if article:
                    candidates.append(article)
            if len(candidates) == 64:
                break

        # Pass 2: fill with secondary items if needed
        if len(candidates) < 64:
            for cluster in clusters:
                for item in cluster.get("news", [])[1:]:
                    article = extract_item(item)
                    if article:
                        candidates.append(article)
                    if len(candidates) == 64:
                        break
                if len(candidates) == 64:
                    break

        # Verify images in parallel
        checks   = await asyncio.gather(*[image_ok(a["image"]) for a in candidates])
        articles = [a for a, ok in zip(candidates, checks) if ok][:24]

        # Sort by date, most recent first
        articles.sort(key=lambda a: a.get("published_at") or "", reverse=True)

        # Always save latest successful response to DB
        cache_set(country, language, articles)

        return {"articles": articles, "total": len(articles), "cached": False}

    except HTTPException:
        raise
    except Exception as e:
        if cached:
            return {"articles": cached["articles"], "total": len(cached["articles"]), "cached": True}
        raise HTTPException(status_code=500, detail=str(e))