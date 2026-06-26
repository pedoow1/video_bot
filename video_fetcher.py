# video_fetcher.py - IA Advanced Search بـ queries ذكية + فلاتر صارمة

import os
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION  = 4.0
CLIP_MAX_DURATION  = 30.0
TARGET_VIDEO_DURATION = 300

IA_SEARCH_URL    = "https://archive.org/advancedsearch.php"
IA_DOWNLOAD_BASE = "https://archive.org/download"
IA_METADATA_BASE = "https://archive.org/metadata"

# ──────────────────────────────────────────
# Queries مخصصة جداً — كلها حيوانات حقيقية
# ──────────────────────────────────────────
# الـ query بتستخدم IA Lucene syntax:
#   title: للبحث في العنوان بس
#   subject: للبحث في الموضوع
#   mediatype:movies يضمن إنها فيديو
#   AND NOT لاستبعاد الكارتون والأنيميشن

IA_QUERIES = [
    # مواقف مضحكة مع كلمة funny لازم تكون في العنوان
    'title:(funny cats fails) AND mediatype:movies AND NOT subject:animation',
    'title:(funny dogs fails) AND mediatype:movies AND NOT subject:animation',
    'title:(animals funny moments) AND mediatype:movies AND NOT subject:animation',
    'title:(funny animal fails compilation) AND mediatype:movies AND NOT subject:animation',
    'title:(pets funny moments) AND mediatype:movies AND NOT subject:animation',
    'title:(hilarious animals) AND mediatype:movies AND NOT subject:animation',
    'title:(funny animal reactions) AND mediatype:movies AND NOT subject:animation',
    'title:(animals being silly) AND mediatype:movies AND NOT subject:animation',
    'title:(cats being funny) AND mediatype:movies AND NOT subject:animation',
    'title:(dogs being funny) AND mediatype:movies AND NOT subject:animation',
    'title:(funny animal clips) AND mediatype:movies AND NOT subject:animation',
    'title:(animals try not to laugh) AND mediatype:movies AND NOT subject:animation',
]

# كلمات لو اتلاقت في العنوان → استبعاد
BLACKLIST_WORDS = [
    "cartoon", "animation", "animated", "anime", "looney", "tunes",
    "tom and jerry", "mickey", "disney", "pixar", "documentary",
    "lecture", "tutorial", "training", "news", "interview",
    "movie trailer", "horror", "science", "history", "nature film",
    "wildlife documentary", "facts about", "education",
    "reaction", "reacting", "react", "watching", "compilation reacts",
    # استبعاد الفيديوهات العامة اللي مش فيها مواقف مضحكة
    "cute animals", "baby animals", "adorable", "relaxing",
    "satisfying", "calming", "beautiful", "amazing nature",
]

# لازم يكون في العنوان كلمة "funny" أو "hilarious" أو "fails" أو "silly" + حيوان
FUNNY_REQUIRED = [
    "funny", "hilarious", "fails", "fail", "silly", "humor",
    "humorous", "comedy", "lol", "laugh", "moments",
    "try not to laugh", "being silly", "being funny",
]

ANIMAL_REQUIRED = [
    "cat", "cats", "kitten", "kittens", "dog", "dogs", "puppy", "puppies",
    "animal", "animals", "pet", "pets", "bird", "parrot", "rabbit",
    "hamster", "goat", "duck", "monkey", "raccoon", "otter",
]


# ──────────────────────────────────────────
# ffmpeg helpers
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
# فلتر صارم على نتائج البحث
# ──────────────────────────────────────────

def _is_real_animal_video(title: str, subject) -> bool:
    title_lower = title.lower()
    subj_lower  = (subject if isinstance(subject, str) else " ".join(subject or [])).lower()
    combined    = title_lower + " " + subj_lower

    # استبعاد لو فيه blacklist
    if any(bw in combined for bw in BLACKLIST_WORDS):
        return False

    # لازم يكون فيه حيوان
    if not any(aw in combined for aw in ANIMAL_REQUIRED):
        return False

    # لازم يكون فيه كلمة تدل على إنه مضحك — ده الفلتر الأساسي
    if not any(fw in combined for fw in FUNNY_REQUIRED):
        return False

    return True


# ──────────────────────────────────────────
# IA Search
# ──────────────────────────────────────────

def _search_ia(query: str, rows: int = 20) -> list:
    try:
        params = {
            "q":      query,
            "fl[]":   ["identifier", "title", "subject", "downloads"],
            "rows":   rows,
            "page":   random.randint(1, 5),
            "output": "json",
            "sort[]": "downloads desc",
        }
        r = requests.get(IA_SEARCH_URL, params=params, timeout=15)
        if r.status_code != 200:
            return []

        docs    = r.json().get("response", {}).get("docs", [])
        results = []
        for d in docs:
            identifier = d.get("identifier", "")
            title      = d.get("title", "") or ""
            subject    = d.get("subject", [])
            if not identifier:
                continue
            if _is_real_animal_video(title, subject):
                results.append({
                    "identifier": identifier,
                    "title":      title,
                    "downloads":  d.get("downloads", 0),
                })
        return results

    except Exception as e:
        print(f"  ⚠️ IA search خطأ: {e}")
        return []


# ──────────────────────────────────────────
# جلب ملفات الفيديو من item
# ──────────────────────────────────────────

def _get_mp4_files(identifier: str) -> list:
    try:
        r = requests.get(f"{IA_METADATA_BASE}/{identifier}", timeout=15)
        if r.status_code != 200:
            return []

        files       = r.json().get("files", [])
        video_files = []
        for f in files:
            name = f.get("name", "")
            fmt  = f.get("format", "").lower()
            size = int(f.get("size", 0))
            if (
                (name.lower().endswith(".mp4") or "mpeg4" in fmt or "h.264" in fmt)
                and 500_000 < size < 8_000_000   # 500KB → 8MB (فيديوهات قصيرة 10-30 ثانية فقط)
                and not name.startswith("_")
            ):
                video_files.append({
                    "url":  f"{IA_DOWNLOAD_BASE}/{identifier}/{requests.utils.quote(name)}",
                    "name": name,
                    "size": size,
                })

        # الملف المتوسط الحجم أفضل (مش أصغر ولا أكبر)
        video_files.sort(key=lambda x: abs(x["size"] - 3_000_000))
        return video_files[:2]

    except Exception as e:
        print(f"  ⚠️ metadata خطأ ({identifier}): {e}")
        return []


# ──────────────────────────────────────────
# تحميل كليب
# ──────────────────────────────────────────

def _download_clip(url: str, identifier: str, title: str, clip_duration: float) -> dict | None:
    safe   = identifier[:35].replace("/", "_").replace(" ", "_")
    clip_path = os.path.join(CLIPS_DIR, f"ia_{safe}.mp4")
    tmp       = os.path.join(CLIPS_DIR, f"_tmp_{safe}.mp4")

    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
        print(f"  ✅ كاش: {safe}")
        return {"path": clip_path, "description": title, "ia_url": f"https://archive.org/details/{identifier}"}

    try:
        print(f"  ⬇️ {identifier} ...")
        r = requests.get(url, stream=True, timeout=120,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            print(f"  ⚠️ HTTP {r.status_code}")
            return None

        downloaded = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > 150_000_000:
                    break

        if os.path.getsize(tmp) < 500_000:
            return None

        if _cut_clip(tmp, clip_path, clip_duration):
            print(f"  ✅ جاهز ({os.path.getsize(clip_path)//1024} KB) — {title[:50]}")
            return {"path": clip_path, "description": title, "ia_url": f"https://archive.org/details/{identifier}"}
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
    os.makedirs(CLIPS_DIR, exist_ok=True)

    if clip_duration is None:
        clip_duration = min(TARGET_VIDEO_DURATION / count, CLIP_MAX_DURATION)
        print(f"🕐 مدة كل كليب: {clip_duration:.1f}s")

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ كاش جاهز ({count} كليب)")
        return random.sample(existing, count)

    clips  = list(existing)
    needed = count - len(clips)

    # جمع نتائج من كل الـ queries
    print(f"\n🔍 بيبحث في IA عن فيديوهات حيوانات حقيقية...")
    all_items = []
    queries   = random.sample(IA_QUERIES, min(5, len(IA_QUERIES)))

    for q in queries:
        results = _search_ia(q, rows=15)
        print(f"  ✅ '{q[:50]}...' → {len(results)} نتيجة بعد الفلتر")
        all_items.extend(results)
        time.sleep(0.3)

    # إزالة تكرار + ترتيب بالـ downloads
    seen   = set()
    unique = []
    for it in all_items:
        if it["identifier"] not in seen:
            seen.add(it["identifier"])
            unique.append(it)
    unique.sort(key=lambda x: x["downloads"], reverse=True)

    print(f"\n📋 {len(unique)} فيديو بعد الفلتر — جاري التحميل...")

    for item in unique:
        if len(clips) >= count:
            break

        identifier = item["identifier"]
        title      = item["title"]

        mp4_files = _get_mp4_files(identifier)
        if not mp4_files:
            print(f"  ⚠️ مفيش mp4 في {identifier}")
            continue

        result = _download_clip(mp4_files[0]["url"], identifier, title, clip_duration)
        if result:
            clips.append(result)

    # كرر لو ناقص
    if 0 < len(clips) < count:
        while len(clips) < count:
            clips.append(random.choice(clips))

    print(f"\n✅ {len(clips[:count])} كليب جاهز!")
    return clips[:count]


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
    print("🧪 اختبار IA search...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c["path"]) // 1024 if os.path.exists(c["path"]) else 0
        print(f"  - {os.path.basename(c['path'])} ({sz} KB) | {c['description'][:60]}")
