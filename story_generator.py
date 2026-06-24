# story_generator.py - توليد محتوى "10 Amazing Facts" بـ Mistral

import json
import re
import requests
from config import MISTRAL_API_KEY

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

def pick_topic() -> str:
    """يسأل Mistral يختار موضوع مميز لفيديو حقائق"""

    prompt = """You are a viral YouTube content strategist specializing in "Amazing Facts" channels.

Suggest ONE unique and highly engaging topic for a "10 Amazing Facts" YouTube video.

Reply with ONLY the topic as a short phrase (e.g. "10 mind-blowing facts about the placebo effect").
No explanation, no extra text, just the topic phrase."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 40000,
        "temperature": 0.9,
    }

    try:
        response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        topic = response.json()["choices"][0]["message"]["content"].strip().strip('"')
        print(f"💡 الموضوع المختار: {topic}")
        return topic
    except Exception as e:
        print(f"⚠️ فشل اختيار الموضوع: {e} — هنستخدم موضوع افتراضي")
        return "10 mind-blowing facts about the human brain"


def generate_story(topic: str = None) -> dict:
    """يولد القصة فقط — بدون scene keywords (تتولد لاحقاً بعد TTS)"""

    chosen_topic = topic or pick_topic()

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
  "title": "catchy title starting with a number or question (under 70 chars)",
  "description": "engaging YouTube description (80-100 words, ends with CTA to like and subscribe)",
  "tags": ["facts", "amazingfacts", "didyouknow", "tag4", "tag5", "tag6", "tag7", "tag8"],
  "story_paragraphs": [
    "Fact 1: [Fact title]. [3-4 sentences explaining it with wow factor]",
    "Fact 2: [Fact title]. [3-4 sentences explaining it with wow factor]",
    "... exactly 10 items total ..."
  ],
  "bg_keyword": "single English word representing the main topic (e.g. space, ocean, brain, egypt)",
  "mood": "epic"
}}

CRITICAL: story_paragraphs must contain EXACTLY 10 items. Count them before responding.
Do NOT include full_story or scene_keywords — they are handled separately."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 40000,
        "temperature": 0.7,
        "response_format": {"type": "json_object"},
    }

    print(f"📝 جاري توليد محتوى عن: {chosen_topic}")

    try:
        response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"]

        raw = re.sub(r"```json|```", "", raw).strip()
        raw = raw.replace("\u2018", "'").replace("\u2019", "'")
        raw = raw.replace("\u201c", '"').replace("\u201d", '"')

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            if not raw.rstrip().endswith("}"):
                raw = raw.rstrip().rstrip(",") + "\n]}\n" if '"story_paragraphs"' in raw else raw + "\n}"
            raw = re.sub(r',\s*([}\]])', r'\1', raw)
            data = json.loads(raw)

        # full_story من story_paragraphs مباشرة
        data["full_story"] = " ".join(data.get("story_paragraphs", []))

        data.setdefault("bg_keyword", "space")
        data.setdefault("mood", "epic")
        data.setdefault("tags", ["facts", "amazingfacts", "didyouknow"])

        # validation: لازم 10 حقائق
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
    يولد برومبت صورة لكل حقيقة — يُستدعى من main.py بعد انتهاء TTS.
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

Reply with JSON ONLY in this exact shape:
{{"queries": ["search query for fact 1", "search query for fact 2", ...]}}

Exactly {len(paragraphs)} items in the list. No extra text, no markdown."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "mistral-small-2506",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 40000,
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(3):
        try:
            response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            raw = re.sub(r"```json|```", "", raw).strip()

            data = json.loads(raw)
            prompts = data.get("queries", [])

            if isinstance(prompts, list) and len(prompts) == len(paragraphs):
                print(f"✅ برومبتات الصور جاهزة ({len(prompts)} مشهد)")
                for i, p in enumerate(prompts):
                    print(f"   حقيقة {i+1}: {p}")
                return prompts
            else:
                print(f"⚠️ محاولة {attempt+1}: رجع {len(prompts)} بدل {len(paragraphs)} — retry")
                continue

        except Exception as e:
            print(f"⚠️ محاولة {attempt+1} فشلت: {e} — retry")
            continue

    print("❌ فشل توليد برومبتات الصور بعد 3 محاولات")
    raise RuntimeError("generate_scene_image_prompts فشل — مش هنكمل")


if __name__ == "__main__":
    story = generate_story()
    print(f"\nالعنوان: {story['title']}")
    print(f"الموود: {story['mood']}")
    print(f"\nأول حقيقة:\n{story['story_paragraphs'][0]}")
