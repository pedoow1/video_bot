# video_fetcher.py - GPT-4o يختار فيديوهات حيوانات من Internet Archive

import os
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR, GITHUB_TOKEN

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 30.0
TARGET_VIDEO_DURATION = 300  # 5 دقايق

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
IA_SEARCH_URL     = "https://archive.org/advancedsearch.php"
IA_DOWNLOAD_BASE  = "https://archive.org/download"
IA_METADATA_BASE  = "https://archive.org/metadata"


# ──────────────────────────────────────────
# ffprobe / ffmpeg helpers
# ──────────────────────────────────────────

def _get_duration(path: str) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=15,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def _cut_clip(src: str, out_path: str, target_duration: float) -> bool:
    vid_dur = _get_duration(src)
    if not vid_dur or vid_dur < CLIP_MIN_DURATION:
        return False

    cut_dur   = min(target_duration, vid_dur, CLIP_MAX_DURATION)
    max_start = max(0.0, vid_dur - cut_dur)
    start     = random.uniform(0, max_start) if max_start > 0 else 0.0

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", str(round(start, 2)),
        "-i", src,
        "-t", str(round(cut_dur, 2)),
        "-vf", (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1"
        ),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        out_path,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=90)
    return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 10_000


# ──────────────────────────────────────────
# Step 1: GPT-4o يختار identifiers من IA
# ──────────────────────────────────────────

def _ask_gpt_for_ia_identifiers(count: int) -> list:
    """
    بيسأل GPT-4o يدور في Internet Archive ويختار identifiers
    لفيديوهات حيوانات مضحكة حقيقية.
    يرجع list of { "identifier": str, "title": str, "reason": str }
    """
    if not GITHUB_TOKEN:
        print("  ⚠️ GH_TOKEN مش موجود — fallback للبحث العادي")
        return []

    prompt = f"""You are a researcher finding funny animal videos on Internet Archive (archive.org).

Search Internet Archive and give me {count} real video items that contain genuine funny animal footage.

Requirements:
- Must be actual animal videos (cats, dogs, birds, wildlife, pets) — NOT cartoons, animations, or documentaries
- Must be funny, cute, or entertaining animal behavior
- Must be publicly accessible on archive.org
- Prefer short compilations or clips (under 30 minutes)
- The identifier must be a real archive.org item

Good examples of what to look for:
- Funny cat compilations
- Cute dog videos
- Animals being silly or clumsy
- Pet fails and funny moments
- Wildlife doing unexpected things

You MUST use your knowledge of real archive.org identifiers. Do not invent identifiers.

Reply with JSON ONLY:
{{
  "items": [
    {{"identifier": "real-archive-org-id", "title": "video title", "reason": "why it's funny animals"}},
    ...
  ]
}}

Exactly {count} items. Only real archive.org identifiers you are confident exist."""

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.3,
    }

    for attempt in range(3):
        try:
            print(f"  🤖 GPT-4o بيختار identifiers (محاولة {attempt+1})...")
            r = requests.post(GITHUB_MODELS_URL, headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            raw  = r.json()["choices"][0]["message"]["content"]
            raw  = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            items = data.get("items", [])
            if items:
                print(f"  ✅ GPT-4o اختار {len(items)} item")
                for it in items:
                    print(f"     • {it['identifier']} — {it['title'][:50]}")
                return items
        except Exception as e:
            print(f"  ⚠️ محاولة {attempt+1} فشلت: {e}")
            time.sleep(2)

    return []


# ──────────────────────────────────────────
# Step 2: التحقق من الـ identifier في IA
# ──────────────────────────────────────────

def _verify_and_get_files(identifier: str) -> list:
    """
    يتحقق إن الـ identifier موجود فعلاً في IA ويجيب ملفات الفيديو منه.
    يرجع list of { "url": str, "name": str, "size": int }
    """
    try:
        r = requests.get(f"{IA_METADATA_BASE}/{identifier}", timeout=15)
        if r.status_code != 200:
            print(f"  ⚠️ {identifier}: مش موجود في IA (status {r.status_code})")
            return []

        files = r.json().get("files", [])
        video_files = []
        for f in files:
            name = f.get("name", "")
            fmt  = f.get("format", "").lower()
            size = int(f.get("size", 0))
            if (
                (name.lower().endswith(".mp4") or "mpeg4" in fmt or "h.264" in fmt)
                and size > 500_000
                and size < 500_000_000
                and not name.startswith("_")
            ):
                video_files.append({
                    "url":  f"{IA_DOWNLOAD_BASE}/{identifier}/{requests.utils.quote(name)}",
                    "name": name,
                    "size": size,
                })

        # رتب بالحجم — متوسط الحجم أفضل
        video_files.sort(key=lambda x: abs(x["size"] - 50_000_000))
        return video_files[:3]

    except Exception as e:
        print(f"  ⚠️ metadata خطأ ({identifier}): {e}")
        return []


# ──────────────────────────────────────────
# Step 3: لو GPT-4o فشل — بحث عادي في IA
# ──────────────────────────────────────────

# كلمات دي بتأكد إن النتيجة حيوانات فعلاً
_ANIMAL_KWS = [
    "cat", "dog", "kitten", "puppy", "animal", "pet", "bird", "parrot",
    "rabbit", "hamster", "monkey", "panda", "raccoon", "fox", "otter",
    "funny", "cute", "compilation", "wildlife",
]

_IA_FALLBACK_QUERIES = [
    "funny cat compilation",
    "funny dog compilation",
    "funny animals compilation",
    "cute kitten video",
    "cute puppy funny",
    "funny pet video",
    "funny parrot talking",
    "animals being silly",
]


def _search_ia_fallback(query: str, rows: int = 15) -> list:
    try:
        params = {
            "q":     f"({query}) AND mediatype:movies",
            "fl[]": ["identifier", "title"],
            "rows":  rows,
            "page":  random.randint(1, 3),
            "output": "json",
            "sort[]": "downloads desc",
        }
        r = requests.get(IA_SEARCH_URL, params=params, timeout=15)
        if r.status_code != 200:
            return []
        docs = r.json().get("response", {}).get("docs", [])
        results = []
        for d in docs:
            if not d.get("identifier"):
                continue
            title = (d.get("title", "") or "").lower()
            if any(kw in title for kw in _ANIMAL_KWS):
                results.append({
                    "identifier": d["identifier"],
                    "title":      d.get("title", query),
                    "reason":     f"IA search: {query}",
                })
        return results
    except Exception as e:
        print(f"  ⚠️ IA fallback بحث فشل ({query}): {e}")
        return []


# ──────────────────────────────────────────
# Step 4: تحميل الكليبات
# ──────────────────────────────────────────

def _download_clip(video_file: dict, identifier: str, title: str, clip_duration: float) -> dict | None:
    clip_id   = f"ia_{identifier[:35]}".replace("/", "_").replace(" ", "_")
    clip_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
    tmp       = os.path.join(CLIPS_DIR, f"_tmp_{clip_id}.mp4")

    # كاش
    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
        print(f"  ✅ كاش: {clip_id}")
        return {"path": clip_path, "description": title, "ia_url": f"https://archive.org/details/{identifier}"}

    try:
        size_mb = video_file["size"] // 1024 // 1024
        print(f"  ⬇️ {identifier} / {video_file['name']} ({size_mb}MB)...")
        r = requests.get(video_file["url"], stream=True, timeout=120)
        if r.status_code != 200:
            print(f"  ⚠️ تحميل فشل: {r.status_code}")
            return None

        downloaded = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > 150_000_000:  # max 150MB
                    break

        if not os.path.exists(tmp) or os.path.getsize(tmp) < 500_000:
            return None

        if _cut_clip(tmp, clip_path, clip_duration):
            print(f"  ✅ جاهز ({os.path.getsize(clip_path)//1024} KB)")
            return {"path": clip_path, "description": title, "ia_url": f"https://archive.org/details/{identifier}"}
        else:
            print(f"  ⚠️ cut فشل")
            return None

    except Exception as e:
        print(f"  ⚠️ خطأ: {e}")
        return None
    finally:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass


# ──────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────

def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    يرجع list of dicts: { "path", "description", "ia_url" }
    """
    os.makedirs(CLIPS_DIR, exist_ok=True)

    if clip_duration is None:
        clip_duration = min(TARGET_VIDEO_DURATION / count, CLIP_MAX_DURATION)
        print(f"🕐 مدة كل كليب: {clip_duration:.1f}s")

    # كاش موجود؟
    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين في الكاش")
        return random.sample(existing, count)

    clips  = list(existing)
    needed = count - len(clips)

    # ── Step 1: GPT-4o يختار identifiers ──
    print(f"\n🤖 GPT-4o بيختار {needed + 3} فيديو من Internet Archive...")
    gpt_items = _ask_gpt_for_ia_identifiers(needed + 3)  # نطلب أكتر للـ safety

    # ── Step 2: لو GPT-4o فشل — fallback ──
    if not gpt_items:
        print("  ⚠️ GPT-4o مرجعش — بيبحث عادي في IA...")
        queries = random.sample(_IA_FALLBACK_QUERIES, min(4, len(_IA_FALLBACK_QUERIES)))
        for q in queries:
            gpt_items.extend(_search_ia_fallback(q))
            time.sleep(0.5)
        # إزالة تكرار
        seen = set()
        unique = []
        for it in gpt_items:
            if it["identifier"] not in seen:
                seen.add(it["identifier"])
                unique.append(it)
        gpt_items = unique

    random.shuffle(gpt_items)

    # ── Step 3: تحميل الكليبات ──
    for item in gpt_items:
        if len(clips) >= count:
            break

        identifier = item["identifier"]
        title      = item["title"]

        print(f"\n  🔍 تحقق من: {identifier}")
        video_files = _verify_and_get_files(identifier)

        if not video_files:
            print(f"  ⚠️ مفيش فيديو mp4 في {identifier}")
            continue

        result = _download_clip(video_files[0], identifier, title, clip_duration)
        if result:
            clips.append(result)

    # كرر لو ناقص
    if 0 < len(clips) < count:
        print(f"  ⚠️ عندنا {len(clips)} من {count} — بنكرر")
        while len(clips) < count:
            clips.append(random.choice(clips))

    result = clips[:count]
    print(f"\n✅ {len(result)} كليب جاهز!")
    return result


def _get_existing_clips() -> list:
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = []
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4") and not f.startswith("_tmp"):
            full = os.path.join(CLIPS_DIR, f)
            if os.path.getsize(full) > 10_000:
                clips.append({"path": full, "description": f"cached: {f}", "ia_url": ""})
    random.shuffle(clips)
    return clips


def clear_clips_cache():
    if not os.path.exists(CLIPS_DIR):
        return
    n = 0
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4"):
            try:
                os.remove(os.path.join(CLIPS_DIR, f))
                n += 1
            except OSError:
                pass
    print(f"🗑️ مسح {n} كليب")


if __name__ == "__main__":
    print("🧪 اختبار GPT-4o + IA fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c["path"]) // 1024 if os.path.exists(c["path"]) else 0
        print(f"  - {os.path.basename(c['path'])} ({sz} KB) | {c['description'][:60]}")
