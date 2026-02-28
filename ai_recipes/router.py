from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

router = APIRouter()

# ── Models ───────────────────────────────────────────────

class RecipeIngredient(BaseModel):
    name: str
    quantity: str

class AIRecipeRequest(BaseModel):
    query: str       # Always returns English — frontend handles translation
    servings: int = 4  # Number of servings requested by user

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
    prompt = f"""
You are a professional chef. Generate a detailed recipe based on: "{request.query}".
The recipe must be scaled for exactly {request.servings} servings.

Return ONLY valid JSON in ENGLISH with exactly these fields:
{{
  "title": "Recipe name",
  "servings": "{request.servings} servings",
  "prep_time": "e.g. 15 minutes",
  "cook_time": "e.g. 30 minutes",
  "ingredients": [
    {{"name": "ingredient name", "quantity": "amount + unit scaled for {request.servings} servings, e.g. 200 g or 2 cups"}}
  ],
  "instructions": [
    "Step 1 description.",
    "Step 2 description."
  ]
}}

Rules:
- Scale ALL ingredient quantities precisely for {request.servings} servings
- Every ingredient MUST have a specific quantity with units
- Instructions must be clear, separate strings per step
- Return ONLY the JSON object, always in English
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[
                {"role": "system", "content": "You are a professional chef that returns only valid JSON in English."},
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