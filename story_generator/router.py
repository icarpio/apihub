from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter(prefix="/api/story", tags=["story-generator"])

# ── Models ────────────────────────────────────────────────

class StoryRequest(BaseModel):
    characters: str      # e.g. "a brave knight named Leo, a cunning fox"
    setting: str         # e.g. "a enchanted forest in medieval times"
    genre: str = "fantasy"  # fantasy, adventure, mystery, romance, horror, sci-fi, comedy
    length: str = "medium"  # short (~300w), medium (~600w), long (~1000w)

class StoryResponse(BaseModel):
    title: str
    genre: str
    characters: str
    setting: str
    story: str
    moral: Optional[str] = None

# ── Endpoint ──────────────────────────────────────────────

@router.post("", response_model=StoryResponse)
async def generate_story(request: StoryRequest):
    if not request.characters.strip() or not request.setting.strip():
        raise HTTPException(status_code=400, detail="Characters and setting are required.")

    word_counts = {"short": 300, "medium": 600, "long": 1000}
    word_count = word_counts.get(request.length, 600)

    prompt = f"""
You are a master storyteller. Write an original, captivating short story with these elements:
- Characters: {request.characters}
- Setting: {request.setting}
- Genre: {request.genre}
- Length: approximately {word_count} words

Return ONLY valid JSON in ENGLISH with exactly these fields:
{{
  "title": "The story title",
  "genre": "{request.genre}",
  "characters": "{request.characters}",
  "setting": "{request.setting}",
  "story": "The full story text with paragraph breaks using \\n\\n",
  "moral": "A one-sentence moral or theme of the story (optional, null if not applicable)"
}}

Rules:
- Write an engaging, original story with a clear beginning, middle and end
- Use vivid descriptions and natural dialogue
- The story must be entirely in English
- Return ONLY the JSON object, no markdown, no extra text
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a creative storyteller that returns only valid JSON in English."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        for key in ["title", "story"]:
            if key not in data:
                raise ValueError(f"Missing field: '{key}'")
        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating story: {str(e)}")