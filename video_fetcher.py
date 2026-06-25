# video_fetcher.py - جلب مقاطع حيوانات مضحكة من يوتيوب بـ yt-dlp

import os
import random
import subprocess
import json
import time
import re
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 30.0

TARGET_VIDEO_DURATION = 300  # 5 دقايق = 300 ثانية

# كلمات بحث يوتيوب
YOUTUBE_QUERIES = [
    "funny animals compilation",
    "funny cats and dogs",
    "cute funny animals",
    "funny animal moments",
    "hilarious animals",
    "funny pets compilation",
    "cute kittens funny",
    "funny dogs fails",
    "animals being silly",
    "funny wildlife moments",
    "cute baby animals funny",
    "funny raccoon videos",
]


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


def _sanitize_id(video_id: str) -> str:
    """يطهر الـ video ID عشان يكون اسم ملف آمن"""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', video_id)


# ──────────────────────────────────────────
# yt-dlp search & download
# ──────────────────────────────────────────

def _search_youtube(query: str, max_results: int = 20) -> list:
    """
    يبحث يوتيوب بـ yt-dlp ويرجع list of dicts:
      { "id": str, "url": str, "title": str, "duration": int }
    """
    try:
        search_url = f"ytsearch{max_results}:{query}"
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-playlist",
            "--match-filter", "duration > 10 & duration < 180",
            "--quiet",
            search_url,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 and not r.stdout.strip():
            print(f"  ⚠️ yt-dlp بحث فشل ({query}): {r.stderr[:100]}")
            return []

        results = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                info = json.loads(line)
                dur = info.get("duration", 0) or 0
                if dur < CLIP_MIN_DURATION or dur > 180:
                    continue
                results.append({
                    "id":       info.get("id", ""),
                    "url":      info.get("webpage_url", f"https://www.youtube.com/watch?v={info.get('id','')}"),
                    "title":    info.get("title", query),
                    "duration": dur,
                })
            except json.JSONDecodeError:
                continue
        return results
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ yt-dlp انتهت المهلة ({query})")
        return []
    except Exception as e:
        print(f"  ⚠️ yt-dlp خطأ ({query}): {e}")
        return []


def _download_video(url: str, video_id: str) -> str | None:
    """
    يحمل الفيديو بـ yt-dlp ويرجع المسار المؤقت، أو None لو فشل
    """
    safe_id = _sanitize_id(video_id)
    tmp_path = os.path.join(CLIPS_DIR, f"_tmp_{safe_id}.mp4")

    # لو موجود مسبقاً
    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
        return tmp_path

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--quiet",
        "-o", tmp_path,
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
            return tmp_path
        else:
            print(f"  ⚠️ تحميل فشل: {r.stderr[:100] if r.stderr else 'unknown'}")
            return None
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ انتهت مهلة التحميل ({video_id})")
        return None
    except Exception as e:
        print(f"  ⚠️ خطأ في التحميل ({video_id}): {e}")
        return None


# ──────────────────────────────────────────
# Main YouTube fetcher
# ──────────────────────────────────────────

def _fetch_from_youtube(count: int, clip_duration: float) -> list:
    """
    يرجع list of dicts:
      { "path": str, "description": str, "youtube_url": str }
    """
    print(f"  🎬 YouTube — جاري البحث عن {count} فيديو...")
    clips = []

    # اختار queries عشوائية
    queries = random.sample(YOUTUBE_QUERIES, min(len(YOUTUBE_QUERIES), 4))
    all_videos = []

    for q in queries:
        print(f"  🔍 بحث: {q}")
        videos = _search_youtube(q, max_results=15)
        print(f"     وجدنا {len(videos)} نتيجة")
        all_videos.extend(videos)
        time.sleep(0.5)  # تأخير خفيف

    # إزالة المكررات بالـ ID
    seen = set()
    unique_videos = []
    for v in all_videos:
        if v["id"] not in seen:
            seen.add(v["id"])
            unique_videos.append(v)

    random.shuffle(unique_videos)
    print(f"  📋 إجمالي فيديوهات فريدة: {len(unique_videos)}")

    for video in unique_videos:
        if len(clips) >= count:
            break

        safe_id = _sanitize_id(video["id"])
        clip_path = os.path.join(CLIPS_DIR, f"yt_{safe_id}.mp4")

        # لو الكليب موجود مسبقاً
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append({
                "path":         clip_path,
                "description":  video["title"],
                "youtube_url":  video["url"],
            })
            print(f"  ✅ كاش [{len(clips)}/{count}]: {video['title'][:50]}")
            continue

        print(f"  ⬇️ [{len(clips)+1}/{count}] {video['title'][:50]}...")

        # تحميل
        tmp_path = _download_video(video["url"], video["id"])
        if not tmp_path:
            continue

        # قطع الكليب
        dur = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
        if _cut_clip(tmp_path, clip_path, dur):
            size_kb = os.path.getsize(clip_path) // 1024
            print(f"  ✅ جاهز ({size_kb} KB)")
            clips.append({
                "path":         clip_path,
                "description":  video["title"],
                "youtube_url":  video["url"],
            })
        else:
            print(f"  ⚠️ قطع الكليب فشل")

        # حذف الملف المؤقت
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    return clips


# ──────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────

def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    يرجع list of dicts:
      { "path": str, "description": str, "youtube_url": str }

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
        print(f"✅ {count} كليب موجودين — مش محتاج تحميل")
        return random.sample(existing, count)

    clips = list(existing)
    needed = count - len(clips)

    print(f"🎥 جاري جلب {needed} مقطع من YouTube...")
    yt_clips = _fetch_from_youtube(needed, clip_duration)
    clips.extend(yt_clips)

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
                    "path":         full_path,
                    "description":  f"cached clip: {f}",
                    "youtube_url":  "",
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
    print("🧪 اختبار YouTube fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c["path"]) // 1024 if os.path.exists(c["path"]) else 0
        print(f"  - {os.path.basename(c['path'])} ({sz} KB) | {c['description'][:60]}")
