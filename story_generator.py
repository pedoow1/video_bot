# story_generator.py - توليد القصص بـ Mistral

import json
import re
import requests
from config import MISTRAL_API_KEY

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

TOPICS = [
    "a mysterious horror story in an abandoned village",
    "a touching love story set in wartime",
    "a fantasy adventure in a parallel world",
    "a human story about someone who transforms their life",
    "a mysterious puzzle in an ancient city",
    "a science fiction story about the future",
    "a story about friends' loyalty in the hardest of times",
    "an adventure in the depths of the ocean",
    "an AI that discovers its own emotions",
    "a murder mystery in a historic mansion",
]


def generate_story(topic: str = None) -> dict:
    """يولد قصة قصيرة مع كل بيانات الفيديو"""

    import random
    chosen_topic = topic or random.choice(TOPICS)

    prompt = f"""You are a professional short-story writer. Write a gripping short story IN ENGLISH about: {chosen_topic}

Story requirements:
- 750-900 words total
- A striking opening line that hooks the reader immediately
- Rising tension with real suspense
- A surprising or emotionally impactful ending
- Polished, literary, engaging style
- Split into EXACTLY 15 paragraphs (3-4 sentences each, no more, no less)

Reply with JSON ONLY, no extra text, in exactly this shape:
{{
  "title": "catchy, curiosity-driven title (under 70 characters)",
  "description": "engaging YouTube description (150-200 words, hooks without spoiling)",
  "tags": ["story", "shortstory", "tag3", "tag4", "tag5", "tag6", "tag7"],
  "story_paragraphs": [
    "Paragraph 1 of exactly 15...",
    "Paragraph 2 of exactly 15...",
    "Paragraph 3 of exactly 15..."
  ],
  "full_story": "the complete story text, unsplit...",
  "bg_keyword": "overall English theme word for fallback backgrounds (e.g. forest, night, ocean, desert)",
  "mood": "mysterious"
}}

CRITICAL: story_paragraphs must contain EXACTLY 15 items. Count them before responding.
Important: DO NOT include scene_keywords in this response — they will be generated separately."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8000,
        "temperature": 0.7,
    }

    print(f"📝 جاري توليد قصة عن: {chosen_topic}")

    try:
        response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]

        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)

        if "full_story" not in data or not data["full_story"]:
            data["full_story"] = " ".join(data.get("story_paragraphs", []))

        data.setdefault("bg_keyword", "dark forest")
        data.setdefault("mood", "mysterious")
        data.setdefault("tags", ["story", "shortstory"])

        # ── validation: لازم يكون 15 فقرة بالظبط ──
        paras = data.get("story_paragraphs", [])
        if len(paras) != 15:
            print(f"⚠️ Mistral رجّع {len(paras)} فقرة بدل 15 — جاري التصحيح...")
            if len(paras) > 15:
                data["story_paragraphs"] = paras[:15]
            else:
                # لو أقل، بنكرر آخر فقرة عشان نكمل العدد
                while len(data["story_paragraphs"]) < 15:
                    data["story_paragraphs"].append(data["story_paragraphs"][-1])
            print(f"✅ تم التصحيح: {len(data['story_paragraphs'])} فقرة")

        print(f"✅ القصة جاهزة: {data['title']}")

        # ─── الخطوة الجديدة: توليد برومبت صورة مخصص لكل فقرة ───
        paragraphs = data.get("story_paragraphs", [])
        print(f"\n🎨 جاري توليد برومبتات الصور لكل مشهد ({len(paragraphs)} مشهد)...")
        scene_keywords = generate_scene_image_prompts(paragraphs, data["title"], data["bg_keyword"])
        data["scene_keywords"] = scene_keywords

        return data

    except json.JSONDecodeError as e:
        print(f"❌ خطأ في تحليل JSON: {e}")
        print(f"الرد الخام: {raw[:300]}")
        raise
    except requests.RequestException as e:
        print(f"❌ خطأ في الاتصال بـ Mistral: {e}")
        raise


def generate_scene_image_prompts(paragraphs: list, story_title: str, bg_keyword: str) -> list:
    """
    يسأل Mistral يولد برومبت صورة AI مخصص لكل فقرة بناءً على محتواها الفعلي.
    ده بيضمن إن كل مشهد بصري متعلق بالأحداث الفعلية في الفقرة دي بالتحديد.
    """
    paragraphs_text = "\n\n".join(
        f"[Scene {i+1}]: {p}" for i, p in enumerate(paragraphs)
    )

    prompt = f"""You are an AI image prompt specialist. I have a story called "{story_title}".

For EACH scene below, write ONE short image generation prompt (5-10 words) that:
- Captures what is SPECIFICALLY happening or described in THAT scene
- Is vivid and visual (describes setting, action, mood, or key object)
- Is suitable for anime/illustration style image generation
- Does NOT repeat the same prompt across scenes

Story scenes:
{paragraphs_text}

Reply with JSON ONLY — a list of exactly {len(paragraphs)} strings, one per scene, in order:
["prompt for scene 1", "prompt for scene 2", ...]

No extra text, no markdown, just the JSON array."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.5,
    }

    try:
        response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]
        raw = re.sub(r"```json|```", "", raw).strip()
        prompts = json.loads(raw)

        if isinstance(prompts, list) and len(prompts) == len(paragraphs):
            print(f"✅ برومبتات الصور جاهزة ({len(prompts)} مشهد)")
            for i, p in enumerate(prompts):
                print(f"   مشهد {i+1}: {p}")
            return prompts
        else:
            print(f"⚠️ عدد البرومبتات ({len(prompts) if isinstance(prompts, list) else '?'}) != عدد الفقرات ({len(paragraphs)}) — fallback لـ bg_keyword")
            return [bg_keyword] * len(paragraphs)

    except Exception as e:
        print(f"⚠️ فشل توليد برومبتات الصور ({e}) — fallback لـ bg_keyword")
        return [bg_keyword] * len(paragraphs)


if __name__ == "__main__":
    story = generate_story()
    print(f"\nالعنوان: {story['title']}")
    print(f"الموود: {story['mood']}")
    print(f"\nأول فقرة:\n{story['story_paragraphs'][0]}")
    print(f"\nبرومبتات الصور:")
    for i, kw in enumerate(story['scene_keywords']):
        print(f"  مشهد {i+1}: {kw}")
