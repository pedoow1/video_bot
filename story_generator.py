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

    prompt = f"""You are an energetic, charismatic YouTube narrator — like the voice of Bright Side or Facts Verse.

Write a full video SCRIPT in ENGLISH about: {chosen_topic}

The script must feel like a real human is talking to camera — NOT reading a list of facts.

Script structure (EXACTLY in this order):
1. HOOK (1 scene): Start with something like "Hey guys, welcome back! Today we're diving into [topic] — and trust me, some of these will absolutely blow your mind. Let's get into it!"
2. FACTS (8 scenes): Present 8 genuinely surprising facts, each as a natural monologue. Between facts use transitions like "Now here's where it gets crazy...", "But wait, it gets better...", "I know, right? But check this out..."
3. OUTRO (1 scene): End with "And that's a wrap! Which fact shocked you the most? Drop it in the comments below. And if you enjoyed this video, smash that like button and subscribe so you never miss a video. I'll catch you in the next one!"

Rules:
- Talk TO the viewer — say "you", "guys", "we", "your"
- Each scene is 3-5 sentences of natural speech
- Make it fun, warm, and conversational — NOT robotic or encyclopedic
- No bullet points, no "Fact 1:" labels — just natural speech
- EXACTLY 10 scenes total (1 hook + 8 facts + 1 outro)

Reply with JSON ONLY:
{{
  "title": "catchy title starting with a number or question (under 70 chars)",
  "description": "engaging YouTube description (80-100 words, ends with CTA to like and subscribe)",
  "tags": ["facts", "amazingfacts", "didyouknow", "tag4", "tag5", "tag6", "tag7", "tag8"],
  "story_paragraphs": [
    "Hey guys, welcome back! ...",
    "Okay so first up — ...",
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


def generate_scene_descriptions(paragraphs: list, story_title: str) -> list:
    """
    يولد وصف تفصيلي للصورة المثالية لكل حقيقة —
    GPT-4o هيستخدم الوصف ده يدور على الصورة الحقيقية.
    """
    paragraphs_text = "\n\n".join(
        f"[Fact {i+1}]: {p}" for i, p in enumerate(paragraphs)
    )

    prompt = f"""You are a visual researcher for a YouTube facts video titled: "{story_title}"

For EACH scene below, write a search description for finding the perfect real photograph.

Follow these rules STRICTLY:

1. FAMOUS PERSON mentioned → write: "Photo of [Full Name], [brief who they are], [physical appearance or notable feature]"
   Example: "Photo of Dr. John Hollowman, American scientist known for hibernation research, wearing a lab coat in a laboratory setting"

2. ANIMAL → write the species name + specific visual detail
   Example: "A brown bear in deep hibernation inside a cave den, curled up, eyes closed"

3. PLACE or LOCATION → name the exact place + what makes it visually distinctive
   Example: "Inside a NASA cryogenics laboratory with silver pods and tubes, scientists in white suits"

4. OBJECT or CONCEPT → describe what it physically looks like in real life
   Example: "Close-up of a human brain scan MRI showing neural activity patterns lit up in bright colors"

5. EVENT or EXPERIMENT → describe the scene as if it's a photograph
   Example: "Scientists in hazmat suits monitoring frozen human cells under microscope in a sterile lab"

NEVER write vague or generic descriptions like "a person doing something" or "related to the topic".
ALWAYS be specific enough that searching for this description online would find the exact right image.

Scenes:
{paragraphs_text}

Reply with JSON ONLY:
{{"descriptions": [
  "description for scene 1",
  "description for scene 2",
  ...
]}}

Exactly {len(paragraphs)} items."""

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
            descriptions = data.get("descriptions", [])

            if isinstance(descriptions, list) and len(descriptions) == len(paragraphs):
                print(f"✅ أوصاف المشاهد جاهزة ({len(descriptions)} مشهد)")
                for i, d in enumerate(descriptions):
                    print(f"   مشهد {i+1}: {d[:80]}...")
                return descriptions
            else:
                print(f"⚠️ محاولة {attempt+1}: رجع {len(descriptions)} بدل {len(paragraphs)} — retry")
                continue

        except Exception as e:
            print(f"⚠️ محاولة {attempt+1} فشلت: {e} — retry")
            continue

    raise RuntimeError("generate_scene_descriptions فشل بعد 3 محاولات")


def generate_funny_animals_script(topic: str = None) -> dict:
    """
    يولد سكريبت لفيديو حيوانات مضحكة عامة (مش قطط بس).
    المذيع بيتفاعل مع المشهد بشكل كوميدي — بدون ادعاء تفاصيل مش موجودة.
    الفيديو ~5 دقائق (10 مشاهد × ~30 ثانية).
    """
    chosen_topic = topic or "funny animals doing silly things"

    prompt = f"""You are a funny, energetic YouTube narrator for a viral funny animals compilation channel.

Write a video script for: "{chosen_topic}"

The script has EXACTLY 10 short scenes. Each scene is a GENERAL funny reaction to an animal clip —
WITHOUT claiming specific details about what the animal is doing (because we don't know the exact clip).

CORRECT style — general reactions that work for ANY funny animal clip:
- "Look at this guy — he has absolutely no idea what he's doing, and honestly, same."
- "The confidence! The audacity! This animal woke up and chose chaos today."
- "I don't know what's happening here, but I love it. This is peak animal behavior right there."
- "When you think you're the boss but life has other plans... watch this."
- "Scientists say animals don't have emotions. Scientists have clearly never seen this."

WRONG style (NEVER do this — it makes false claims):
- "Watch this cat knock over the glass on purpose" (too specific)
- "This dog is chasing the mailman" (we don't know the clip)
- "Look how this parrot says hello" (too specific)

Rules:
- Each scene: 2-4 sentences of funny, punchy commentary
- React with GENERAL humor that fits ANY funny animal moment
- Never describe specific actions — be funny about the VIBE, the ENERGY, the MOOD
- Mix different animals: dogs, cats, birds, monkeys, raccoons, pandas — variety!
- Use "this animal", "this guy", "this creature", "our hero" — not species unless very generic
- Talk to viewer: "watch this", "you won't believe it", "I can't"
- Keep energy HIGH — this is a 5-minute compilation
- EXACTLY 10 scenes

The title MUST say "5 Minutes" since the video is ~5 minutes long.

Reply with JSON ONLY:
{{
  "title": "funny animals title under 60 chars — MUST include '5 Minutes' (e.g. 'Animals Being Idiots for 5 Minutes')",
  "description": "YouTube description 60-80 words, funny tone, mentions funny animals compilation, ends with CTA",
  "tags": ["funnyanimals", "animals", "cute", "compilation", "funnypets", "animalsbeingidiots", "funny", "lol"],
  "story_paragraphs": [
    "scene 1 narration...",
    "scene 2 narration...",
    "... exactly 10 items ..."
  ],
  "bg_keyword": "animals",
  "mood": "happy"
}}

CRITICAL: story_paragraphs must contain EXACTLY 10 items. Title MUST contain '5 Minutes'."""

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type":  "application/json"
    }
    payload = {
        "model":           "mistral-small-2506",
        "messages":        [{"role": "user", "content": prompt}],
        "max_tokens":      40000,
        "temperature":     0.85,
        "response_format": {"type": "json_object"},
    }

    print(f"📝 جاري توليد سكريبت حيوانات مضحكة: {chosen_topic}")

    try:
        response = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        raw  = response.json()["choices"][0]["message"]["content"]
        raw  = re.sub(r"```json|```", "", raw).strip()
        data = json.loads(raw)

        data["full_story"] = " ".join(data.get("story_paragraphs", []))
        data.setdefault("bg_keyword", "animals")
        data.setdefault("mood", "happy")
        data.setdefault("tags", ["funnyanimals", "animals", "compilation", "funny"])

        # تأكد إن العنوان فيه "5 Minutes"
        title = data.get("title", "")
        if "5 Minutes" not in title and "5 minutes" not in title:
            data["title"] = title.rstrip(".!") + " for 5 Minutes"

        paras = data.get("story_paragraphs", [])
        if len(paras) != 10:
            print(f"⚠️ رجّع {len(paras)} بدل 10 — جاري التصحيح...")
            if len(paras) > 10:
                data["story_paragraphs"] = paras[:10]
            else:
                while len(data["story_paragraphs"]) < 10:
                    data["story_paragraphs"].append(data["story_paragraphs"][-1])

        print(f"✅ السكريبت جاهز: {data['title']}")
        return data

    except Exception as e:
        print(f"❌ خطأ في توليد سكريبت الحيوانات: {e}")
        raise


# للتوافق مع الكود القديم
def generate_cat_script(topic: str = None) -> dict:
    """wrapper للتوافق — بيستدعي generate_funny_animals_script"""
    return generate_funny_animals_script(topic)


if __name__ == "__main__":
    story = generate_story()
    print(f"\nالعنوان: {story['title']}")
    print(f"الموود: {story['mood']}")
    print(f"\nأول حقيقة:\n{story['story_paragraphs'][0]}")

