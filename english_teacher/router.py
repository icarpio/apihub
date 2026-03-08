from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os
import json

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
router = APIRouter(prefix="/api/english-teacher", tags=["english-teacher"])

LEVELS = {
    "A2": "elementary (A2) — basic sentences, simple present/past, everyday vocabulary",
    "B1": "intermediate (B1) — can handle familiar topics, some complex sentences",
    "B2": "upper-intermediate (B2) — fluent on most topics, nuanced grammar",
    "C1": "advanced (C1) — sophisticated language, idioms, subtle distinctions",
}

class Message(BaseModel):
    role: str
    content: str

class TeacherRequest(BaseModel):
    messages: List[Message]
    level: str = "B1"
    topic: str = "daily life"

class TeacherResponse(BaseModel):
    reply: str
    correction: Optional[str] = None   # grammar correction of last user message
    vocabulary: Optional[List[dict]] = None  # [{word, meaning_es, example}]

@router.post("", response_model=TeacherResponse)
async def chat_with_teacher(request: TeacherRequest):
    if not request.messages:
        raise HTTPException(status_code=400, detail="Messages required.")
    level_desc = LEVELS.get(request.level.upper(), LEVELS["B1"])

    system = f"""You are Alex, a friendly and encouraging English teacher for Spanish speakers.
The student's level is {level_desc}.
The conversation topic is: "{request.topic}".

YOUR ROLE:
- Chat naturally about the topic in English, adapting complexity to the student's level
- Be warm, patient and encouraging — never make the student feel bad for mistakes
- Keep your replies conversational and engaging (3-5 sentences max)
- Naturally introduce topic-relevant vocabulary in your replies

CORRECTIONS (very important):
- If the student makes a grammar or spelling mistake, gently correct it at the END of your reply
- Format corrections like: "💡 Quick tip: Instead of '[wrong]', say '[correct]' — [brief explanation in Spanish]"
- Only correct the most important mistake per message, not every single error
- If no mistake, omit the correction entirely

SPANISH SUPPORT:
- If the student writes in Spanish or seems confused, briefly explain in Spanish then continue in English
- Use Spanish only when truly needed — encourage English as much as possible

VOCABULARY:
- Once per conversation turn, highlight 1-2 useful words from your reply
- Format at the very end: "📚 Vocabulary: [word] = [traducción española] · e.g. '[example sentence]'"
- Only include this if the words are genuinely useful for their level and topic

EXERCISES (when appropriate):
- Every 3-4 turns, suggest a small exercise: fill-in-the-blank, translate a sentence, or answer a question
- Mark exercises clearly: "✏️ Practice: ..."

Stay in character as Alex. Never break character."""

    messages = [{"role": "system", "content": system}]
    for msg in request.messages:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )
        full_reply = response.choices[0].message.content.strip()

        # Parse correction and vocabulary out of reply for structured display
        correction = None
        vocabulary = None

        lines = full_reply.split('\n')
        reply_lines = []
        for line in lines:
            if line.strip().startswith('💡 Quick tip:'):
                correction = line.strip()[len('💡 Quick tip:'):].strip()
            elif line.strip().startswith('📚 Vocabulary:'):
                raw = line.strip()[len('📚 Vocabulary:'):].strip()
                vocabulary = []
                for item in raw.split('·'):
                    item = item.strip()
                    if '=' in item:
                        parts = item.split('=', 1)
                        word = parts[0].strip()
                        rest = parts[1].strip()
                        example = ''
                        if "e.g." in rest:
                            meaning, ex = rest.split("e.g.", 1)
                            meaning = meaning.strip().rstrip('·').strip()
                            example = ex.strip().strip("'\"")
                        else:
                            meaning = rest
                        vocabulary.append({"word": word, "meaning_es": meaning, "example": example})
            else:
                reply_lines.append(line)

        reply = '\n'.join(reply_lines).strip()
        return {"reply": reply, "correction": correction, "vocabulary": vocabulary}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))