# story_generator.py - توليد محتوى "10 Amazing Facts" بـ Mistral

import json
import re
import requests
from config import MISTRAL_API_KEY

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

TOPICS = [
    "10 mind-blowing facts about Ancient Egypt",
    "10 incredible facts about the human brain",
    "10 shocking facts about outer space",
    "10 amazing facts about the deep ocean",
    "10 surprising facts about animals that will blow your mind",
    "10 unbelievable facts about ancient Rome",
    "10 fascinating facts about the human body",
    "10 crazy facts about the universe that science just discovered",
    "10 mind-blowing facts about quantum physics",
    "10 shocking facts about volcanoes and earthquakes",
    "10 amazing facts about the Amazon rainforest",
    "10 incredible facts about black holes",
    "10 surprising facts about dreams and sleep",
    "10 unbelievable facts about ancient civilizations",
    "10 mind-blowing facts about DNA and genetics",
    "10 fascinating facts about the moon",
    "10 shocking facts about prehistoric creatures",
    "10 amazing facts about extreme weather phenomena",
    "10 incredible facts about the human immune system",
    "10 surprising facts about mathematics hidden in nature",
]


def generate_story(topic: str = None) -> dict:
    """يولد فيديو '10 Amazing Facts' مع كل بيانات الفيديو"""

    import random
    chosen_topic = topic or random.choice(TOPICS)

    prompt = f"""You are a professional YouTube content creator specializing in "Did You Know?" and "Amazing Facts" videos.

Create a "10 Amazing Facts" video script IN ENGLISH about: {chosen_topic}

Requirements:
- EXACTLY 10 facts, each one genuinely surprising and mind-blowing
- Each fact should be 3-4 sentences: state the fact, explain it, add a wow detail
- Hook the viewer immediately with the most shocking fact first
- Use conversational, energetic tone like Bright Side or Facts Verse
- Each fact must be a standalone "scene" — no cliffhangers between facts

Reply with JSON ONLY, no extra text, in exactly this shape:
{{
  "title": "catchy title starting with a number or question (under 70 chars, e.g. '10 Mind-Blowing Facts About Space That Will Shock You')",
  "description": "engaging YouTube description (150-200 words, teases the facts without spoiling them, ends with CTA to like and subscribe)",
  "tags": ["facts", "amazingfacts", "didyouknow", "tag4", "tag5", "tag6", "tag7", "tag8"],
  "story_paragraphs": [
    "Fact 1: [Fact title]. [3-4 sentences explaining it with wow factor]",
    "Fact 2: [Fact title]. [3-4 sentences explaining it with wow factor]",
    "... exactly 10 items total ..."
  ],
  "full_story": "all 10 facts combined as one continuous text",
  "bg_keyword": "single English word representing the main topic (e.g. space, ocean, brain, egypt)",
  "mood": "epic"
}}

CRITICAL: story_paragraphs must contain EXACTLY 10 items — one per fact. Count them before responding.
Important: DO NOT include scene_keywords in this response — they will be generated separately."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 6000,
        "temperature": 0.7,
    }

    print(f"📝 جاري توليد محتوى عن: {chosen_topic}")

    try:
        response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]

        raw = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)

        if "full_story" not in data or not data["full_story"]:
            data["full_story"] = " ".join(data.get("story_paragraphs", []))

        data.setdefault("bg_keyword", "space")
        data.setdefault("mood", "epic")
        data.setdefault("tags", ["facts", "amazingfacts", "didyouknow"])

        # ── validation: لازم يكون 10 حقائق بالظبط ──
        paras = data.get("story_paragraphs", [])
        if len(paras) != 10:
            print(f"⚠️ Mistral رجّع {len(paras)} فقرة بدل 10 — جاري التصحيح...")
            if len(paras) > 10:
                data["story_paragraphs"] = paras[:10]
            else:
                while len(data["story_paragraphs"]) < 10:
                    data["story_paragraphs"].append(data["story_paragraphs"][-1])
            print(f"✅ تم التصحيح: {len(data['story_paragraphs'])} حقائق")

        print(f"✅ المحتوى جاهز: {data['title']}")

        # ─── توليد برومبت صورة مخصص لكل حقيقة ───
        paragraphs = data.get("story_paragraphs", [])
        print(f"\n🎨 جاري توليد برومبتات الصور لكل حقيقة ({len(paragraphs)} مشهد)...")
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
    يسأل Mistral يولد برومبت صورة AI مخصص لكل حقيقة بناءً على محتواها الفعلي.
    """
    paragraphs_text = "\n\n".join(
        f"[Fact {i+1}]: {p}" for i, p in enumerate(paragraphs)
    )

    prompt = f"""You are a Google image search expert for a "10 Amazing Facts" YouTube channel.

For EACH fact below, write ONE short Google image search query (2-5 words) that:
- Searches for a real photo that visually represents the fact
- Uses simple, specific keywords a person would type in Google Images
- Returns high-quality real photos (not illustrations or diagrams)
- Does NOT repeat the same query across facts

Examples of good search queries:
- "ancient egyptian pyramids aerial view"
- "human brain neurons closeup"
- "deep ocean anglerfish"
- "black hole nasa"
- "amazon rainforest canopy"

Facts:
{paragraphs_text}

Reply with JSON ONLY — a list of exactly {len(paragraphs)} strings, one per fact, in order:
["search query for fact 1", "search query for fact 2", ...]

No extra text, no markdown, just the JSON array."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
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
                print(f"   حقيقة {i+1}: {p}")
            return prompts
        else:
            print(f"⚠️ عدد البرومبتات غلط — fallback لـ bg_keyword")
            return [bg_keyword] * len(paragraphs)

    except Exception as e:
        print(f"⚠️ فشل توليد برومبتات الصور ({e}) — fallback لـ bg_keyword")
        return [bg_keyword] * len(paragraphs)


if __name__ == "__main__":
    story = generate_story()
    print(f"\nالعنوان: {story['title']}")
    print(f"الموود: {story['mood']}")
    print(f"\nأول حقيقة:\n{story['story_paragraphs'][0]}")
    print(f"\nبرومبتات الصور:")
    for i, kw in enumerate(story['scene_keywords']):
        print(f"  حقيقة {i+1}: {kw}")
