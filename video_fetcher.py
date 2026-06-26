import os
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR

CLIPS_DIR     = os.path.join(OUTPUT_DIR, "cat_clips")
USED_IDS_FILE = os.path.join(OUTPUT_DIR, "used_identifiers.json")

CLIP_MIN_DURATION  = 4.0
CLIP_MAX_DURATION  = 25.0
TARGET_VIDEO_DURATION = 300

# نتجاهل أول وآخر فترة من كل فيديو مصدر (إنترو/أوترو/لوجو غالباً)
SKIP_START_SECONDS = 10.0
SKIP_END_SECONDS   = 10.0

IA_SEARCH_URL    = "https://archive.org/advancedsearch.php"
IA_DOWNLOAD_BASE = "https://archive.org/download"
IA_METADATA_BASE = "https://archive.org/metadata"

FAILARMY_IDENTIFIER = "FailArmy-Archive"

ANIMAL_FILENAME_WORDS = [
    "animal", "cat", "dog", "pet", "bird", "wildlife",
    "kitten", "puppy", "goat", "duck", "monkey",
]

IA_QUERIES = [
    'title:(funny cats fails) AND mediatype:movies',
    'title:(funny dogs fails) AND mediatype:movies',
    'title:(animal fails compilation) AND mediatype:movies',
    'title:(funny animals) AND mediatype:movies',
]

BLACKLIST_WORDS = [
    "cartoon", "animation", "animated", "anime",
    "tom and jerry", "mickey", "disney", "pixar",
    "documentary", "lecture", "tutorial", "training",
    "news", "interview", "horror", "science",
    "reaction", "reacting", "react to", "watching",
    "relaxing", "calming", "satisfying", "sleep",
    "nature sounds", "asmr",
]

FUNNY_WORDS = [
    "funny", "hilarious", "fails", "fail", "silly",
    "humor", "comedy", "lol", "laugh", "amusing",
    "being silly", "being funny", "chaos", "moments",
]

ANIMAL_WORDS = [
    "cat", "cats", "kitten", "dog", "dogs", "puppy",
    "animal", "animals", "pet", "pets", "bird",
    "parrot", "rabbit", "hamster", "goat", "duck",
    "monkey", "raccoon", "otter", "wildlife",
]


# ──────────────────────────────────────────
# Used identifiers — مع حفظ آخر نقطة قطع
# ──────────────────────────────────────────

def _load_used_ids() -> dict:
    """يرجع dict: {identifier: {"last_pos": float, "completed": bool}}"""
    try:
        if os.path.exists(USED_IDS_FILE):
            with open(USED_IDS_FILE, "r") as f:
                data = json.load(f)
                # دعم الفورمات القديم (list)
                if isinstance(data, list):
                    return {k: {"last_pos": 0, "completed": True} for k in data}
                return data
    except Exception:
        pass
    return {}


def _save_used_id(identifier: str, last_pos: float, completed: bool = False):
    used = _load_used_ids()
    # لو اتكمل خالص، متحدثش الـ position
    if identifier in used and used[identifier].get("completed"):
        return
    used[identifier] = {"last_pos": last_pos, "completed": completed}
    try:
        with open(USED_IDS_FILE, "w") as f:
            json.dump(used, f, indent=2)
    except Exception:
        pass


def _get_next_start(identifier: str, vid_dur: float, clip_duration: float) -> float | None:
    """
    يحسب نقطة البداية التالية للفيديو.
    - بيتجاهل أول SKIP_START_SECONDS وآخر SKIP_END_SECONDS من الفيديو
    - لو الفيديو اتكمل → يرجع None (تجاهله)
    - لو فيه last_pos → يكمل منها
    - لو جديد → يبدأ بعد فترة التجاهل في الأول
    """
    used = _load_used_ids()

    if identifier in used:
        info = used[identifier]
        if info.get("completed"):
            return None  # الفيديو خلص، تجاهله
        last_pos = info.get("last_pos", 0)
    else:
        last_pos = 0

    # أول مرة (last_pos == 0) لازم نتجاوز أول SKIP_START_SECONDS
    next_start = max(last_pos, SKIP_START_SECONDS)

    # أقصى نقطة مسموح نوصلها هي قبل آخر SKIP_END_SECONDS من الفيديو
    usable_end = vid_dur - SKIP_END_SECONDS

    # الفيديو قصير جداً ومفيش جزء صالح بين بداية وآخر التجاهل
    if usable_end <= SKIP_START_SECONDS:
        _save_used_id(identifier, vid_dur, completed=True)
        return None

    # لو مفيش وقت كافي للكليب التالي قبل ما نوصل لآخر الجزء الصالح
    if next_start + clip_duration > usable_end:
        _save_used_id(identifier, vid_dur, completed=True)
        return None

    return next_start


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


def _get_url_duration(url: str) -> float | None:
    """يجيب مدة الفيديو من URL مباشرة بدون تحميل كامل"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error",
             "-show_entries", "format=duration",
             "-of", "json", url],
            capture_output=True, text=True, timeout=20,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def _cut_clip(src: str, out_path: str, target_duration: float) -> bool:
    vid_dur = _get_duration(src)
    if not vid_dur or vid_dur < CLIP_MIN_DURATION:
        return False

    usable_end = vid_dur - SKIP_END_SECONDS
    cut_dur    = min(target_duration, vid_dur, CLIP_MAX_DURATION)
    min_start  = SKIP_START_SECONDS
    max_start  = max(min_start, usable_end - cut_dur)
    start      = random.uniform(min_start, max_start) if max_start > min_start else min_start

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
# فلتر
# ──────────────────────────────────────────

def _is_valid_clip(title: str, subject) -> bool:
    title_lower = title.lower()
    subj_lower  = (subject if isinstance(subject, str) else " ".join(subject or [])).lower()
    combined    = title_lower + " " + subj_lower

    if any(bw in combined for bw in BLACKLIST_WORDS):
        return False

    if not any(aw in combined for aw in ANIMAL_WORDS):
        return False

    return True


# ──────────────────────────────────────────
# IA Search
# ──────────────────────────────────────────

def _search_ia(query: str, rows: int = 30) -> list:
    try:
        params = {
            "q":      query,
            "fl[]":   ["identifier", "title", "subject", "downloads"],
            "rows":   rows,
            "page":   random.randint(1, 10),
            "output": "json",
            "sort[]": "random desc",
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
            if _is_valid_clip(title, subject):
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
# جلب فيديوهات من FailArmy-Archive مباشرة
# ──────────────────────────────────────────

def _get_failarmy_clips(used_ids: dict, count: int) -> list:
    """بيجيب قائمة فيديوهات من FailArmy-Archive مباشرة من الـ metadata"""
    try:
        print(f"  🎬 بيجيب قائمة FailArmy-Archive...")
        r = requests.get(f"{IA_METADATA_BASE}/{FAILARMY_IDENTIFIER}", timeout=30)
        if r.status_code != 200:
            print(f"  ⚠️ FailArmy metadata فشل: {r.status_code}")
            return []

        files = r.json().get("files", [])
        candidates = []
        for f in files:
            name = f.get("name", "")
            fmt  = f.get("format", "").lower()
            size = int(f.get("size", 0) or 0)

            if not (name.lower().endswith(".mp4") or "mpeg4" in fmt):
                continue
            if size < 5_000_000:
                continue
            if name.startswith("_"):
                continue

            file_id = f"{FAILARMY_IDENTIFIER}/{name}"

            # لو اتكمل خالص، تجاهله
            if file_id in used_ids and used_ids[file_id].get("completed"):
                continue

            candidates.append({
                "identifier": file_id,
                "title":      name.replace(".mp4", "").replace(".", " "),
                "url":        f"{IA_DOWNLOAD_BASE}/{FAILARMY_IDENTIFIER}/{requests.utils.quote(name)}",
                "size":       size,
            })

        random.shuffle(candidates)
        result = candidates[:count * 3]
        print(f"  ✅ {len(result)} ملف من FailArmy")
        return result

    except Exception as e:
        print(f"  ⚠️ FailArmy خطأ: {e}")
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
            length = f.get("length", None)
            try:
                dur = float(length) if length else None
            except (ValueError, TypeError):
                dur = None
            name = f.get("name", "")
            fmt  = f.get("format", "").lower()
            size = int(f.get("size", 0))
            if (
                (name.lower().endswith(".mp4") or "mpeg4" in fmt or "h.264" in fmt)
                and 500_000 < size
                and (dur is None or dur <= 60)
                and not name.startswith("_")
            ):
                video_files.append({
                    "url":      f"{IA_DOWNLOAD_BASE}/{identifier}/{requests.utils.quote(name)}",
                    "name":     name,
                    "size":     size,
                    "duration": dur,
                })

        video_files.sort(key=lambda x: x["duration"] if x["duration"] else 9999)
        return video_files[:2]

    except Exception as e:
        print(f"  ⚠️ metadata خطأ ({identifier}): {e}")
        return []


# ──────────────────────────────────────────
# تحميل كليب
# ──────────────────────────────────────────

def _download_clip(url: str, identifier: str, title: str, clip_duration: float) -> dict | None:
    safe = identifier[:35].replace("/", "_").replace(" ", "_")

    # جيب مدة الفيديو الأصلي
    vid_dur = _get_url_duration(url)
    if not vid_dur:
        vid_dur = 600  # افتراضي لو مش عارف

    # جيب نقطة البداية الصحيحة (بعيد عن أول وآخر SKIP_*_SECONDS)
    start = _get_next_start(identifier, vid_dur, clip_duration)
    if start is None:
        print(f"  ⏭️ {identifier[:40]} اتكمل، تخطي")
        return None

    # اسم الكليب يشمل الـ position عشان نفس الفيديو يعمل كليبات مختلفة
    safe_pos  = str(int(start)).zfill(5)
    clip_path = os.path.join(CLIPS_DIR, f"ia_{safe}_{safe_pos}.mp4")

    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
        print(f"  ✅ كاش: {safe}_{safe_pos}")
        _save_used_id(identifier, start + clip_duration)
        return {"path": clip_path, "description": title, "ia_url": f"https://archive.org/details/{identifier}"}

    try:
        print(f"  ✂️ قطع من {start:.1f}s — {identifier[:40]}")

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(round(start, 2)),
            "-i", url,
            "-t", str(round(clip_duration, 2)),
            "-vf", (
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,"
                "setsar=1"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            clip_path,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=120)

        if r.returncode == 0 and os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            next_pos  = start + clip_duration
            # الفيديو يعتبر مكتمل لو القطعة الجاية هتدخل في منطقة آخر SKIP_END_SECONDS
            completed = (next_pos + clip_duration) > (vid_dur - SKIP_END_SECONDS)
            _save_used_id(identifier, next_pos, completed=completed)
            print(f"  ✅ جاهز @ {start:.1f}s→{next_pos:.1f}s {'(مكتمل)' if completed else ''}")
            return {"path": clip_path, "description": title, "ia_url": f"https://archive.org/details/{identifier}"}

        print(f"  ⚠️ ffmpeg فشل: {r.stderr[:200] if r.stderr else 'unknown'}")
        return None

    except Exception as e:
        print(f"  ⚠️ خطأ: {e}")
        return None


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

    clips    = list(existing)
    used_ids = _load_used_ids()

    # ── أولاً: FailArmy-Archive مباشرة ──
    print(f"\n🎬 بيجيب من FailArmy-Archive...")
    failarmy_items = _get_failarmy_clips(used_ids, count - len(clips))

    for item in failarmy_items:
        if len(clips) >= count:
            break
        result = _download_clip(item["url"], item["identifier"], item["title"], clip_duration)
        if result:
            clips.append(result)

    # ── fallback: بحث عام في IA ──
    if len(clips) < count:
        print(f"\n🔍 fallback — بيبحث في IA...")
        all_items = []
        for q in random.sample(IA_QUERIES, min(4, len(IA_QUERIES))):
            results = _search_ia(q, rows=30)
            print(f"  ✅ '{q[:60]}' → {len(results)} نتيجة")
            all_items.extend(results)
            time.sleep(0.3)

        seen   = set()
        unique = []
        for it in all_items:
            if it["identifier"] not in seen and (
                it["identifier"] not in used_ids
                or not used_ids[it["identifier"]].get("completed")
            ):
                seen.add(it["identifier"])
                unique.append(it)
        random.shuffle(unique)

        for item in unique:
            if len(clips) >= count:
                break
            mp4_files = _get_mp4_files(item["identifier"])
            if not mp4_files:
                continue
            result = _download_clip(mp4_files[0]["url"], item["identifier"], item["title"], clip_duration)
            if result:
                clips.append(result)

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
