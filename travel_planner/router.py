from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter(prefix="/api/travel-planner", tags=["travel-planner"])

# ── Models ────────────────────────────────────────────────

class TravelRequest(BaseModel):
    destination: str
    days: int
    travelers: int = 1

class DayActivity(BaseModel):
    time: str          # e.g. "09:00"
    title: str
    description: str
    tip: Optional[str] = None

class DayPlan(BaseModel):
    day: int
    title: str         # e.g. "Arrival & Old Town"
    activities: List[DayActivity]
    lunch: str
    dinner: str

class TravelResponse(BaseModel):
    destination: str
    days: int
    travelers: int
    budget_estimate: str
    accommodation: str
    transport_tips: str
    practical_tips: List[str]
    itinerary: List[DayPlan]

# ── Endpoint ──────────────────────────────────────────────

@router.post("", response_model=TravelResponse)
async def generate_itinerary(request: TravelRequest):
    destination = request.destination.strip()
    if not destination:
        raise HTTPException(status_code=400, detail="Destination is required.")
    if not 1 <= request.days <= 14:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 14.")
    if not 1 <= request.travelers <= 20:
        raise HTTPException(status_code=400, detail="Travelers must be between 1 and 20.")

    prompt = f"""
You are an expert travel planner. Create a detailed {request.days}-day itinerary for {request.travelers} traveler(s) visiting {destination}.

Return ONLY valid JSON in ENGLISH with exactly this structure:
{{
  "destination": "Official destination name",
  "days": {request.days},
  "travelers": {request.travelers},
  "budget_estimate": "Estimated total budget range e.g. $800–$1200 per person",
  "accommodation": "Recommended area/type to stay and 2-3 specific hotel/hostel suggestions",
  "transport_tips": "How to get there and get around (flights, trains, local transport)",
  "practical_tips": [
    "Tip 1 (visa, currency, language...)",
    "Tip 2 (best time to visit, weather...)",
    "Tip 3 (safety, customs, etiquette...)",
    "Tip 4 (must-buy, souvenirs...)"
  ],
  "itinerary": [
    {{
      "day": 1,
      "title": "Short evocative title for the day",
      "activities": [
        {{
          "time": "09:00",
          "title": "Activity name",
          "description": "2-3 sentence description of what to do and see",
          "tip": "Optional insider tip for this activity"
        }}
      ],
      "lunch": "Specific restaurant recommendation with dish to try",
      "dinner": "Specific restaurant recommendation with dish to try"
    }}
  ]
}}

Rules:
- Each day must have 3-5 activities with realistic times
- Activities should flow geographically (minimize travel between them)
- Include mix of iconic sights AND hidden gems
- Budget must account for {request.travelers} traveler(s)
- Return ONLY the JSON object, no markdown, no extra text
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are an expert travel planner that returns only valid JSON in English."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating itinerary: {str(e)}")