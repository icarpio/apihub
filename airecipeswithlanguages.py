from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Literal
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

# Cargar variables de entorno
load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter()

# ── Models ───────────────────────────────────────────────

class RecipeIngredient(BaseModel):
    name: str
    quantity: str

class AIRecipeRequest(BaseModel):
    query: str
    language: Literal["es", "en", "it", "fr"] = "en"

class AIRecipeResponse(BaseModel):
    title: str
    servings: str
    prep_time: str
    cook_time: str
    ingredients: List[RecipeIngredient]
    instructions: List[str]

# ── Endpoint ─────────────────────────────────────────────

@router.post("/api/ai-recipe", response_model=AIRecipeResponse)
async def generate_ai_recipe(request: AIRecipeRequest):
    language_map = {
        "es": "Spanish",
        "en": "English",
        "it": "Italian",
        "fr": "French",
    }

    lang_name = language_map.get(request.language, "English")

    prompt = f"""
You are a professional chef. Generate a detailed recipe based on: "{request.query}".

Return ONLY valid JSON with exactly these fields:
{{
  "title": "Recipe name",
  "servings": "e.g. 4 servings",
  "prep_time": "e.g. 15 minutes",
  "cook_time": "e.g. 30 minutes",
  "ingredients": [
    {{"name": "ingredient name", "quantity": "amount + unit, e.g. 200 g or 2 cups"}}
  ],
  "instructions": [
    "Step 1 description.",
    "Step 2 description."
  ]
}}

Rules:
- Every ingredient MUST have a specific quantity with units
- Instructions must be clear, separate strings per step
- Translate the ENTIRE response into {lang_name}
- Return ONLY the JSON object
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",  # puedes cambiar por otro disponible
            messages=[
                {"role": "system", "content": "You are a professional chef that returns only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        data = json.loads(content)

        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating recipe: {str(e)}")