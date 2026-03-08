from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import httpx
from deep_translator import GoogleTranslator
import os
from dotenv import load_dotenv
from ai_recipes.router import router as ai_recipes_router
from city_history.router import router as city_history_router
from guestbook.router import router as guestbook_router
from english_teacher.router import router as english_teacher_router
from companion.router import router as companion_router
from aisha.router import router as aisha_router
from polls.router import router as polls_router
from story_generator.router import router as story_generator_router
from travel_planner.router import router as travel_planner_router
from insta_posts.router import router as insta_posts_router
from news.router import router as news_router

# Cargar variables de entorno
load_dotenv()

app = FastAPI(title="API Ninjas Hub")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
#Router para otras apps
# ──────────────────────────────────────────────

app.include_router(ai_recipes_router)
app.include_router(city_history_router)
app.include_router(guestbook_router)
app.include_router(english_teacher_router)
app.include_router(companion_router)
app.include_router(aisha_router)
app.include_router(story_generator_router)
app.include_router(polls_router)
app.include_router(travel_planner_router)
app.include_router(insta_posts_router)
app.include_router(news_router)

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
API_KEY = os.getenv("API_KEY")
BASE_URL = "https://api.api-ninjas.com/v1"
HEADERS = {"X-Api-Key": API_KEY}


# ──────────────────────────────────────────────
# Translation endpoint
# ──────────────────────────────────────────────

class TranslateRequest(BaseModel):
    texts: List[str]
    target: str  # "es", "it", "fr"

@app.post("/api/translate")
async def translate_texts(body: TranslateRequest):
    target = body.target if body.target in ("es", "it", "fr") else "es"
    results = []
    for text in body.texts:
        try:
            translated = GoogleTranslator(source="en", target=target).translate(text) if text and len(text) > 2 else text
            results.append(translated)
        except Exception:
            results.append(text)
    return {"translations": results}


# ──────────────────────────────────────────────
# API endpoints — all return raw English data
# ──────────────────────────────────────────────

@app.get("/api/facts")
async def get_facts():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/facts", headers=HEADERS)
        return r.json()


@app.get("/api/history")
async def get_history():
    from datetime import date
    today = date.today()
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/historicalevents",
                             headers=HEADERS,
                             params={"month": today.month, "day": today.day})
        return r.json()


@app.get("/api/weather")
async def get_weather(city: str = "Madrid"):
    async with httpx.AsyncClient() as client:

        # 1️⃣ Obtener coordenadas
        geo_response = await client.get(
            f"{BASE_URL}/geocoding",
            headers=HEADERS,
            params={"city": city}
        )

        if geo_response.status_code != 200:
            return {"error": "Error fetching geolocation"}

        geo_data = geo_response.json()

        if not geo_data:
            return {"error": "City not found"}

        lat = geo_data[0]["latitude"]
        lon = geo_data[0]["longitude"]

        # 2️⃣ Obtener clima
        weather_response = await client.get(
            f"{BASE_URL}/weather",
            headers=HEADERS,
            params={"lat": lat, "lon": lon}
        )

        if weather_response.status_code != 200:
            return {"error": "Error fetching weather"}

        weather_data = weather_response.json()

        # Añadimos el nombre real devuelto
        weather_data["city"] = city

        return weather_data

@app.get("/api/recipes")
async def get_recipes(query: str = "pasta"):
    async with httpx.AsyncClient() as client:
        # v3 uses "title" param, endpoint is /v3/recipe
        base_v3 = BASE_URL.replace("/v1", "/v3")
        r = await client.get(f"{base_v3}/recipe",
                             headers=HEADERS,
                             params={"title": query})
        return r.json()


@app.get("/api/cocktails")
async def get_cocktails(name: str = "margarita"):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/cocktail",
                             headers=HEADERS,
                             params={"name": name})
        return r.json()

@app.get("/api/worldtime")
async def get_worldtime(city: str = "Madrid"):
    async with httpx.AsyncClient() as client:
        # Step 1: geocode city → lat/lon via Nominatim (free, no key needed)
        geo = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "api-hub/1.0"},
            timeout=10.0
        )
        geo_data = geo.json()
        if not geo_data:
            return {"error": f"City '{city}' not found"}
        lat = geo_data[0]["lat"]
        lon = geo_data[0]["lon"]

        # Step 2: query worldtime with lat/lon
        r = await client.get(
            f"{BASE_URL}/worldtime",
            headers=HEADERS,
            params={"lat": lat, "lon": lon}
        )
        data = r.json()
        # Inject city name so frontend can display it
        data["city"] = geo_data[0].get("display_name", city).split(",")[0]
        return data


@app.get("/api/exercises")
async def get_exercises(
    muscle: str = "biceps",
    difficulty: str | None = None
):
    params = {"muscle": muscle}
    if difficulty:
        params["difficulty"] = difficulty

    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/exercises", headers=HEADERS, params=params)
        return r.json()
    
@app.get("/api/convertcurrency")
async def convert_currency(have: str, want: str, amount: float):
    have = have.strip().upper()
    want = want.strip().upper()
    async with httpx.AsyncClient() as client:
        # Frankfurter: free, no key, all ISO 4217 pairs
        # https://www.frankfurter.app/docs/
        r = await client.get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": have, "to": want}
        )
        data = r.json()
        # Response: {"amount":100,"base":"USD","date":"2024-01-15","rates":{"EUR":91.23}}
        if "rates" not in data or want not in data.get("rates", {}):
            return {"error": data.get("message", f"Cannot convert {have} to {want}. Check the currency codes.")}
        return {
            "old_amount":  amount,
            "old_currency": have,
            "new_currency": want,
            "new_amount":  data["rates"][want],
            "date":        data.get("date", "")
        }

@app.get("/api/qrcode")
async def get_qrcode(
    data: str,
    format: str = "png",
    fg_color: str = "000000",
    bg_color: str = "ffffff"
):
    import base64
    # Accept header must match the format requested
    mime_map = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "svg": "image/svg+xml",
        "eps": "application/postscript",
    }
    accept = mime_map.get(format, "image/png")
    qr_headers = {**HEADERS, "Accept": accept}

    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/qrcode",
            headers=qr_headers,
            params={"data": data, "format": format,
                    "fg_color": fg_color, "bg_color": bg_color}
        )
        encoded = base64.b64encode(r.content).decode("utf-8")
        return {"image": encoded, "format": format, "mime": accept}

@app.get("/api/randomimage")
async def get_random_image():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/randomimage",
                             headers=HEADERS)
        return {"image": r.text}
    

@app.get("/api/passwordgenerator")
async def get_password(length: int = 16):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/passwordgenerator",
                             headers=HEADERS,
                             params={"length": length})
        return r.json()


@app.get("/api/horoscope")
async def get_horoscope(zodiac: str = "aries"):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/horoscope",
                             headers=HEADERS,
                             params={"zodiac": zodiac.lower()})
        return r.json()


@app.get("/api/quotes")
async def get_quotes(categories: str = "", offset: int = 0, limit: int = 6):
    async with httpx.AsyncClient() as client:
        params = {"offset": offset, "limit": limit}
        if categories:
            params["categories"] = categories
        r = await client.get(f"{BASE_URL.replace('v1','v2')}/quotes",
                             headers=HEADERS, params=params)
        return r.json()


@app.get("/api/barcode")
async def get_barcode(text: str, type: str = "upc"):
    import base64
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/barcodegenerate",
            headers={**HEADERS, "Accept": "image/png"},
            params={"text": text, "type": type}
        )
        encoded = base64.b64encode(r.content).decode("utf-8")
        return {"image": encoded}


