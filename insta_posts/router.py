from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional, List
from openai import OpenAI
from dotenv import load_dotenv
import os, json, base64

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
router = APIRouter(prefix="/api/instagram", tags=["instagram"])

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

@router.post("")
async def generate_post(
    image:    UploadFile = File(...),
    language: str        = Form("es"),
    music:    str        = Form("false"),   # Form sends strings
):
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use JPG, PNG or WebP.")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 10 MB).")

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    mime = image.content_type
    include_music = music.lower() == "true"
    lang_name = "Spanish" if language == "es" else "English"

    music_block = ""
    if include_music:
        music_block = """
- "music": array of 3 song recommendations that perfectly match the vibe and mood of this image/post.
  Each object: {"title": "song name", "artist": "artist name", "reason": "1 sentence why it fits, in the post language"}"""
    else:
        music_block = '- "music": null'

    prompt = f"""You are a professional Instagram content creator and social media strategist.
Analyse this image carefully and generate a compelling Instagram post for it.
Language: {lang_name}

Return ONLY a valid JSON object with these exact keys:
- "caption": professional, engaging Instagram caption based on what you see in the image.
  Use emojis naturally. Strong hook on the first line. Include a call-to-action at the end.
  3-6 sentences. Written entirely in {lang_name}.
- "hashtags": array of exactly 5 highly relevant hashtags (without the # symbol).
  Choose the most impactful tags based on the image content, mood and style.
{music_block}

Return only the JSON. No markdown, no explanation."""

    try:
        r = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text",      "text": prompt},
                ]
            }],
            response_format={"type": "json_object"},
            temperature=0.85,
            max_tokens=800,
        )
        data = json.loads(r.choices[0].message.content.strip())
        return {
            "caption":  data.get("caption", ""),
            "hashtags": data.get("hashtags", [])[:5],
            "music":    data.get("music", None),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))