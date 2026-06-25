# video_fetcher.py - جلب مقاطع قطط مضحكة من Pexels

import os
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 15.0

PEXELS_QUERIES = [
    "funny animal",
    "cute dog funny",
    "funny cat",
    "funny bird",
    "funny monkey",
    "cute kitten",
    "funny raccoon",
    "funny panda",
    "animal fail funny",
    "funny pet video",
    "animals being silly",
    "funny wildlife",
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


# ──────────────────────────────────────────
# Pexels
# ──────────────────────────────────────────

def _fetch_from_pexels(count: int, clip_duration: float) -> list:
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("  ⚠️ PEXELS_API_KEY مش موجود!")
        return []

    print(f"  🎬 Pexels — جاري جلب {count} فيديو...")
    clips = []
    headers = {"Authorization": api_key}

    queries = random.sample(PEXELS_QUERIES, min(len(PEXELS_QUERIES), 4))
    all_videos = []

    for q in queries:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": q, "per_page": 20, "size": "medium"},
                timeout=15,
            )
            if r.status_code != 200:
                print(f"  ⚠️ Pexels رد {r.status_code} على ({q})")
                continue
            for v in r.json().get("videos", []):
                dur = v.get("duration", 0)
                if dur < CLIP_MIN_DURATION or dur > 120:
                    continue
                files = sorted(
                    [f for f in v["video_files"] if f.get("width", 9999) <= 1280],
                    key=lambda f: f.get("width", 0),
                    reverse=True,
                )
                if not files:
                    files = v["video_files"]
                best = files[0]
                all_videos.append({
                    "url":      best["link"],
                    "id":       f"pexels_{v['id']}",
                    "duration": dur,
                })
        except Exception as e:
            print(f"  ⚠️ Pexels بحث فشل ({q}): {e}")

    random.shuffle(all_videos)

    for video in all_videos:
        if len(clips) >= count:
            break
        clip_path = os.path.join(CLIPS_DIR, f"{video['id']}.mp4")
        tmp = os.path.join(CLIPS_DIR, f"_tmp_{video['id']}.mp4")

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append(clip_path)
            continue

        try:
            print(f"  ⬇️ Pexels [{len(clips)+1}/{count}] {video['id']}...")
            r = requests.get(video["url"], stream=True, timeout=60)
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    f.write(chunk)

            dur = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
            if _cut_clip(tmp, clip_path, dur):
                print(f"  ✅ Pexels جاهز ({os.path.getsize(clip_path)//1024} KB)")
                clips.append(clip_path)
            else:
                print(f"  ⚠️ Pexels cut فشل")
        except Exception as e:
            print(f"  ⚠️ Pexels تحميل فشل: {e}")
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
    os.makedirs(CLIPS_DIR, exist_ok=True)

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين — مش محتاج تحميل")
        return random.sample(existing, count)

    clips = list(existing)
    needed = count - len(clips)

    print(f"🐱 جاري جلب {needed} مقطع من Pexels...")
    pexels_clips = _fetch_from_pexels(needed, clip_duration)
    clips.extend(pexels_clips)

    # كرر لو لسه ناقص
    if 0 < len(clips) < count:
        print(f"  ⚠️ عندنا {len(clips)} من {count} — هنكرر")
        while len(clips) < count:
            clips.append(random.choice(clips))

    result = clips[:count]
    print(f"✅ {len(result)} مقطع جاهز!")
    return result


def _get_existing_clips() -> list:
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = [
        os.path.join(CLIPS_DIR, f)
        for f in os.listdir(CLIPS_DIR)
        if f.endswith(".mp4") and not f.startswith("_tmp")
        and os.path.getsize(os.path.join(CLIPS_DIR, f)) > 10_000
    ]
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
    print("🧪 اختبار fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c) // 1024 if os.path.exists(c) else 0
        print(f"  - {os.path.basename(c)} ({sz} KB)")
