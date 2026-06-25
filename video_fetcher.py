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
TARGET_VIDEO_DURATION = 300  # 5 دقايق

# كلمات بحث أقوى وأبسط
YOUTUBE_QUERIES = [
    "funny cats",
    "hilarious cats",
    "funny dogs",
    "cute kittens",
    "cat fails",
    "funny pets",
    "cute funny animals",
    "kittens playing",
    "puppy fails",
    "funny animal videos",
    "hilarious pets",
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
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', video_id)


# ──────────────────────────────────────────
# yt-dlp search
# ──────────────────────────────────────────

def _search_youtube(query: str, max_results: int = 15) -> list:
    """بحث يوتيوب مع أقوى flags"""
    try:
        search_url = f"ytsearch{max_results}:{query}"
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--flat-playlist",
            "--no-playlist",
            "--match-filter", "duration > 15 & duration < 180",
            "--quiet",
            "--no-warnings",
            "--js-runtimes", "deno",
            "--extractor-args", "youtube:player_client=web,ios,android,web_embedded",
            "--ignore-errors",
            search_url,
        ]
        
        print(f"  🔍 بحث: {query}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        print(f"     exit code: {r.returncode} | نتايج: {len(r.stdout.strip().splitlines())} سطر")

        if r.stderr and "ERROR" in r.stderr:
            print(f"     ⚠️ stderr: {r.stderr[-300:]}")

        results = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                info = json.loads(line)
                dur = info.get("duration") or 0
                if dur < CLIP_MIN_DURATION or dur > 180:
                    continue
                results.append({
                    "id":       info.get("id", ""),
                    "url":      info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id','')}",
                    "title":    info.get("title", query),
                    "duration": dur,
                })
            except json.JSONDecodeError:
                continue
                
        print(f"     ✅ وجدنا {len(results)} فيديو صالح")
        return results
        
    except subprocess.TimeoutExpired:
        print(f"  ⚠️ timeout في البحث ({query})")
        return []
    except Exception as e:
        print(f"  ⚠️ خطأ في _search_youtube ({query}): {e}")
        return []


# ──────────────────────────────────────────
# Download
# ──────────────────────────────────────────

def _download_video(url: str, video_id: str) -> str | None:
    safe_id = _sanitize_id(video_id)
    tmp_path = os.path.join(CLIPS_DIR, f"_tmp_{safe_id}.mp4")

    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
        return tmp_path

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=web,ios,android",
        "-o", tmp_path,
        url,
    ]
    
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=150)
        if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
            return tmp_path
        else:
            print(f"  ⚠️ تحميل فشل: {video_id}")
            if r.stderr:
                print(f"     {r.stderr[-200:]}")
            return None
    except Exception as e:
        print(f"  ⚠️ خطأ تحميل ({video_id}): {e}")
        return None


# ──────────────────────────────────────────
# Main Functions
# ──────────────────────────────────────────

def _fetch_from_youtube(count: int, clip_duration: float) -> list:
    print(f"  🎬 YouTube — جاري البحث عن {count} فيديو...")
    clips = []
    queries = random.sample(YOUTUBE_QUERIES, min(len(YOUTUBE_QUERIES), 5))
    all_videos = []

    for q in queries:
        videos = _search_youtube(q)
        all_videos.extend(videos)
        time.sleep(0.8)  # تأخير أكبر شوية

    # إزالة التكرار
    seen = set()
    unique_videos = [v for v in all_videos if v["id"] not in seen and not seen.add(v["id"])]

    random.shuffle(unique_videos)
    print(f"  📋 إجمالي فيديوهات فريدة: {len(unique_videos)}")

    for video in unique_videos:
        if len(clips) >= count:
            break

        clip_path = os.path.join(CLIPS_DIR, f"yt_{_sanitize_id(video['id'])}.mp4")

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append({"path": clip_path, "description": video["title"], "youtube_url": video["url"]})
            continue

        tmp_path = _download_video(video["url"], video["id"])
        if not tmp_path:
            continue

        dur = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
        if _cut_clip(tmp_path, clip_path, dur):
            clips.append({
                "path": clip_path,
                "description": video["title"],
                "youtube_url": video["url"]
            })
            print(f"  ✅ جاهز: {video['title'][:60]}")

        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass

    return clips


def fetch_cat_clips(count: int = 10, clip_duration: float = None) -> list:
    os.makedirs(CLIPS_DIR, exist_ok=True)

    if clip_duration is None:
        clip_duration = TARGET_VIDEO_DURATION / count
        clip_duration = min(clip_duration, CLIP_MAX_DURATION)
        print(f"🕐 مدة كل كليب: {clip_duration:.1f}s")

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ استخدام {count} كليب موجود")
        return random.sample(existing, count)

    needed = count - len(existing)
    print(f"🎥 جاري جلب {needed} مقطع جديد من YouTube...")

    yt_clips = _fetch_from_youtube(needed, clip_duration)
    clips = existing + yt_clips

    # تكرار لو ناقص
    while len(clips) < count and clips:
        clips.append(random.choice(clips))

    result = clips[:count]
    print(f"✅ إجمالي {len(result)} مقطع جاهز!")
    return result


def _get_existing_clips() -> list:
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = []
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4") and not f.startswith("_tmp"):
            full_path = os.path.join(CLIPS_DIR, f)
            if os.path.getsize(full_path) > 10_000:
                clips.append({
                    "path": full_path,
                    "description": f"cached: {f}",
                    "youtube_url": ""
                })
    random.shuffle(clips)
    return clips


def clear_clips_cache():
    if os.path.exists(CLIPS_DIR):
        for f in os.listdir(CLIPS_DIR):
            if f.endswith(".mp4"):
                try:
                    os.remove(os.path.join(CLIPS_DIR, f))
                except:
                    pass
        print("🗑️ تم مسح الكاش")


if __name__ == "__main__":
    print("🧪 اختبار video_fetcher...")
    clips = fetch_cat_clips(count=5)
    print(f"\n✅ تم جلب {len(clips)} كليب")
