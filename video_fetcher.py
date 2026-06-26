# video_fetcher.py - جلب مقاطع فيديو من Internet Archive (مجاني، بدون API key)

import os
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 30.0

TARGET_VIDEO_DURATION = 300  # 5 دقايق = 300 ثانية

# Internet Archive search queries - فيديوهات حيوانات مجانية
IA_QUERIES = [
    "funny cat compilation",
    "funny dog compilation",
    "cute kitten video",
    "funny animals compilation",
    "funny pet video",
    "cute puppy funny",
    "funny parrot video",
    "funny rabbit video",
    "funny hamster video",
    "animals being silly",
]

# كلمات نتجنبها في نتائج IA عشان نضمن إن الفيديو حيوانات فعلاً
IA_ANIMAL_KEYWORDS = [
    "cat", "dog", "kitten", "puppy", "animal", "pet", "bird", "parrot",
    "rabbit", "hamster", "monkey", "panda", "raccoon", "fox", "otter",
    "funny", "cute", "compilation", "wildlife", "nature",
]

# Internet Archive Advanced Search API
IA_SEARCH_URL = "https://archive.org/advancedsearch.php"
IA_DOWNLOAD_BASE = "https://archive.org/download"


# ──────────────────────────────────────────
# Helpers
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

    cut_dur = min(target_duration, vid_dur, CLIP_MAX_DURATION)
    max_start = max(0.0, vid_dur - cut_dur)
    start = random.uniform(0, max_start) if max_start > 0 else 0.0

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
# Internet Archive - البحث عن فيديوهات
# ──────────────────────────────────────────

def _search_ia(query: str, rows: int = 20) -> list:
    """
    يبحث في Internet Archive ويرجع list of dicts:
      { "identifier": str, "title": str, "description": str }
    """
    try:
        params = {
            "q": f"({query}) AND mediatype:movies",
            "fl[]": ["identifier", "title", "description"],
            "rows": rows,
            "page": random.randint(1, 3),  # randomize للتنويع
            "output": "json",
            "sort[]": "downloads desc",    # الأكثر تحميلاً أولاً
        }
        r = requests.get(IA_SEARCH_URL, params=params, timeout=15)
        if r.status_code != 200:
            print(f"  ⚠️ IA بحث فشل ({query}): status {r.status_code}")
            return []
        docs = r.json().get("response", {}).get("docs", [])
        results = []
        for d in docs:
            if not d.get("identifier"):
                continue
            title = (d.get("title", "") or "").lower()
            desc  = (d.get("description", "") or "").lower()
            combined = title + " " + desc
            # فلترة: لازم يحتوي على كلمة حيوان واحدة على الأقل
            if any(kw in combined for kw in IA_ANIMAL_KEYWORDS):
                results.append({
                    "identifier":  d.get("identifier", ""),
                    "title":       d.get("title", query),
                    "description": d.get("description", f"{query} video from Internet Archive"),
                })
        return results
    except Exception as e:
        print(f"  ⚠️ IA بحث خطأ ({query}): {e}")
        return []


def _get_video_files(identifier: str) -> list:
    """
    يجيب ملفات الفيديو لـ item معين من Internet Archive.
    يرجع list of { "url": str, "name": str, "size": int }
    """
    try:
        meta_url = f"https://archive.org/metadata/{identifier}"
        r = requests.get(meta_url, timeout=15)
        if r.status_code != 200:
            return []
        files = r.json().get("files", [])
        video_files = []
        for f in files:
            name = f.get("name", "")
            fmt = f.get("format", "").lower()
            size = int(f.get("size", 0))
            # فلتر: فيديو mp4 أو mpeg4 بس، مش ملفات metadata
            if (
                (name.lower().endswith(".mp4") or "mpeg4" in fmt or "h.264" in fmt)
                and size > 500_000    # أكبر من 500KB
                and size < 500_000_000  # أصغر من 500MB
                and not name.startswith("_")
            ):
                video_files.append({
                    "url":  f"{IA_DOWNLOAD_BASE}/{identifier}/{name}",
                    "name": name,
                    "size": size,
                })
        # رتب بالحجم - متوسط الحجم أحسن (مش أصغر ولا أكبر)
        video_files.sort(key=lambda x: abs(x["size"] - 50_000_000))
        return video_files[:3]  # أحسن 3 اختيارات
    except Exception as e:
        print(f"  ⚠️ IA metadata خطأ ({identifier}): {e}")
        return []


# ──────────────────────────────────────────
# Internet Archive - تحميل الكليبات
# ──────────────────────────────────────────

def _fetch_from_ia(count: int, clip_duration: float) -> list:
    """
    يرجع list of dicts:
      { "path": str, "description": str, "ia_url": str }
    """
    print(f"  🎬 Internet Archive — جاري جلب {count} فيديو...")
    clips = []

    # اجمع نتائج من queries متعددة
    queries = random.sample(IA_QUERIES, min(len(IA_QUERIES), 4))
    all_items = []
    for q in queries:
        items = _search_ia(q, rows=15)
        all_items.extend(items)
        time.sleep(0.5)  # respect rate limits

    # shuffle عشان التنويع
    random.shuffle(all_items)

    # إزالة التكرار
    seen_ids = set()
    unique_items = []
    for item in all_items:
        if item["identifier"] not in seen_ids:
            seen_ids.add(item["identifier"])
            unique_items.append(item)

    for item in unique_items:
        if len(clips) >= count:
            break

        identifier = item["identifier"]
        print(f"  🔍 IA item: {identifier}")

        video_files = _get_video_files(identifier)
        if not video_files:
            print(f"  ⚠️ مفيش فيديو في {identifier}")
            continue

        # جرب أول ملف
        vf = video_files[0]
        clip_id = f"ia_{identifier[:30]}".replace("/", "_").replace(" ", "_")
        clip_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
        tmp = os.path.join(CLIPS_DIR, f"_tmp_{clip_id}.mp4")

        # لو موجود كاش
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append({
                "path":        clip_path,
                "description": item["title"],
                "ia_url":      f"https://archive.org/details/{identifier}",
            })
            print(f"  ✅ كاش موجود: {clip_id}")
            continue

        try:
            print(f"  ⬇️ IA [{len(clips)+1}/{count}] {vf['name']} ({vf['size']//1024//1024}MB)...")
            r = requests.get(vf["url"], stream=True, timeout=120)
            if r.status_code != 200:
                print(f"  ⚠️ تحميل فشل: {r.status_code}")
                continue

            with open(tmp, "wb") as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    f.write(chunk)
                    downloaded += len(chunk)
                    # توقف لو حملنا كفاية (max 100MB)
                    if downloaded > 100_000_000:
                        break

            if not os.path.exists(tmp) or os.path.getsize(tmp) < 500_000:
                print(f"  ⚠️ ملف صغير أو فاشل")
                continue

            dur = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
            if _cut_clip(tmp, clip_path, dur):
                print(f"  ✅ IA جاهز ({os.path.getsize(clip_path)//1024} KB)")
                clips.append({
                    "path":        clip_path,
                    "description": item["title"],
                    "ia_url":      f"https://archive.org/details/{identifier}",
                })
            else:
                print(f"  ⚠️ cut فشل — مدة الفيديو قصيرة أو corrupt")

        except requests.exceptions.Timeout:
            print(f"  ⚠️ timeout في التحميل")
        except Exception as e:
            print(f"  ⚠️ خطأ: {e}")
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    return clips


# ──────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────

def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    يرجع list of dicts:
      { "path": str, "description": str, "ia_url": str }

    clip_duration: لو None بيحسبها تلقائياً عشان الفيديو كله يوصل TARGET_VIDEO_DURATION
    """
    os.makedirs(CLIPS_DIR, exist_ok=True)

    # حساب مدة كل كليب
    if clip_duration is None:
        clip_duration = TARGET_VIDEO_DURATION / count
        clip_duration = min(clip_duration, CLIP_MAX_DURATION)
        print(f"🕐 مدة كل كليب: {clip_duration:.1f}s (تارجت {TARGET_VIDEO_DURATION}s / {count} مشهد)")

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين في الكاش — مش محتاج تحميل")
        return random.sample(existing, count)

    clips = list(existing)
    needed = count - len(clips)

    print(f"🎬 جاري جلب {needed} مقطع من Internet Archive...")
    ia_clips = _fetch_from_ia(needed, clip_duration)
    clips.extend(ia_clips)

    # كرر لو لسه ناقص
    if 0 < len(clips) < count:
        print(f"  ⚠️ عندنا {len(clips)} من {count} — هنكرر")
        while len(clips) < count:
            clips.append(random.choice(clips))

    result = clips[:count]
    print(f"✅ {len(result)} مقطع جاهز!")
    return result


def _get_existing_clips() -> list:
    """يرجع existing clips كـ list of dicts"""
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = []
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4") and not f.startswith("_tmp"):
            full_path = os.path.join(CLIPS_DIR, f)
            if os.path.getsize(full_path) > 10_000:
                clips.append({
                    "path":        full_path,
                    "description": f"cached clip: {f}",
                    "ia_url":      "",
                })
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
    print("🧪 اختبار IA fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c["path"]) // 1024 if os.path.exists(c["path"]) else 0
        print(f"  - {os.path.basename(c['path'])} ({sz} KB) | {c['description'][:60]}")
