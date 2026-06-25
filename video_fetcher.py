# video_fetcher.py - جلب مقاطع قطط مضحكة
# الترتيب: Rumble (--impersonate) → Pexels API (fallback مضمون)

import os
import re
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 15.0

SEARCH_QUERIES = [
    "funny cats",
    "cute funny kittens",
    "cats being silly",
    "funny cat moments",
    "cats fail compilation",
    "hilarious cats",
    "cats vs cucumbers",
    "cats scared funny",
    "kittens playing funny",
    "cats jumping fail",
]

# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def _ensure_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("📦 تثبيت yt-dlp...")
        subprocess.run(["pip", "install", "yt-dlp", "-q", "--break-system-packages"], check=True)

    try:
        import curl_cffi  # noqa
    except ImportError:
        print("📦 تثبيت curl_cffi...")
        subprocess.run(
            ["pip", "install", "curl_cffi>=0.10,<0.15", "-q", "--break-system-packages"],
            check=True,
        )


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
    """يقطع مقطع بالمدة المطلوبة من فيديو موجود."""
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
# Rumble source
# ──────────────────────────────────────────

def _search_rumble(query: str, limit: int = 15) -> list:
    print(f"  🔍 Rumble: {query}")
    try:
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end", str(limit),
            "--dump-json",
            "--no-warnings",
            "--quiet",
            "--impersonate", "chrome:android",
            f"rumble:{query}",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        videos = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            try:
                info = json.loads(line)
                url = info.get("url") or info.get("webpage_url", "")
                duration = info.get("duration") or 999
                if not url or duration > 120:
                    continue
                videos.append({
                    "url":      url,
                    "id":       re.sub(r"[^a-zA-Z0-9]", "_", info.get("id", url[-10:]))[:20],
                    "title":    info.get("title", "")[:60],
                    "duration": duration,
                })
            except json.JSONDecodeError:
                continue

        print(f"     → {len(videos)} فيديو")
        return videos
    except Exception as e:
        print(f"  ⚠️ Rumble بحث فشل ({query}): {e}")
        return []


def _download_rumble_clip(video_url: str, post_id: str, target_duration: float, out_path: str) -> bool:
    tmp = os.path.join(CLIPS_DIR, f"_tmp_{post_id}.mp4")
    try:
        cmd_dl = [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "--merge-output-format", "mp4",
            "--impersonate", "chrome:android",
            "-o", tmp,
            "--no-warnings", "--quiet",
            video_url,
        ]
        r = subprocess.run(cmd_dl, capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(tmp):
            subprocess.run(
                ["yt-dlp", "-f", "best", "--impersonate", "chrome:android",
                 "-o", tmp, "--no-warnings", "--quiet", video_url],
                capture_output=True, timeout=90,
            )

        if not os.path.exists(tmp) or os.path.getsize(tmp) < 5000:
            return False

        return _cut_clip(tmp, out_path, target_duration)

    except Exception as e:
        print(f"    ⚠️ Rumble تحميل فشل: {e}")
        return False
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _fetch_from_rumble(count: int, clip_duration: float) -> list:
    clips = []
    all_videos = []
    queries = random.sample(SEARCH_QUERIES, min(len(SEARCH_QUERIES), 4))
    for q in queries:
        if len(all_videos) >= count * 4:
            break
        all_videos.extend(_search_rumble(q, limit=15))
        time.sleep(1)

    if not all_videos:
        return []

    seen = set()
    unique = []
    for v in all_videos:
        if v["id"] not in seen:
            seen.add(v["id"])
            unique.append(v)
    random.shuffle(unique)

    for video in unique:
        if len(clips) >= count:
            break
        post_id = video["id"]
        duration = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
        clip_path = os.path.join(CLIPS_DIR, f"rumble_{post_id}.mp4")

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append(clip_path)
            continue

        print(f"  ⬇️ Rumble [{len(clips)+1}/{count}] {video['title'][:50]}...")
        if _download_rumble_clip(video["url"], post_id, duration, clip_path):
            print(f"  ✅ جاهز ({os.path.getsize(clip_path)//1024} KB)")
            clips.append(clip_path)
        else:
            print(f"  ⚠️ فشل — التالي")
        time.sleep(0.5)

    return clips


# ──────────────────────────────────────────
# Pexels fallback
# ──────────────────────────────────────────

PEXELS_QUERIES = [
    "funny cat", "cute kitten", "cat playing",
    "cat fail", "silly cat", "kitten funny",
]


def _fetch_from_pexels(count: int, clip_duration: float) -> list:
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        print("  ⚠️ PEXELS_API_KEY مش موجود — مش هينفع Pexels fallback")
        return []

    print(f"  🎬 Pexels fallback — جاري جلب {count} فيديو...")
    clips = []
    headers = {"Authorization": api_key}

    queries = random.sample(PEXELS_QUERIES, min(len(PEXELS_QUERIES), 3))
    all_videos = []

    for q in queries:
        try:
            r = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": q, "per_page": 15, "size": "medium"},
                timeout=15,
            )
            if r.status_code != 200:
                continue
            for v in r.json().get("videos", []):
                dur = v.get("duration", 0)
                if dur < CLIP_MIN_DURATION or dur > 120:
                    continue
                # اختار أفضل ملف ≤ 720p
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
    """
    تجيب `count` مقطع قطط:
      1. بيجرب Rumble أول (impersonate)
      2. لو فشل أو ما كملش → Pexels fallback
    """
    _ensure_ytdlp()
    os.makedirs(CLIPS_DIR, exist_ok=True)

    # استخدم الموجود لو كافي
    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين — مش محتاج تحميل")
        return random.sample(existing, count)

    clips = list(existing)
    needed = count - len(clips)

    # ── المحاولة الأولى: Rumble ──
    print(f"🐱 [1/2] جاري المحاولة من Rumble ({needed} مقطع)...")
    rumble_clips = _fetch_from_rumble(needed, clip_duration)
    clips.extend(rumble_clips)

    # ── Fallback: Pexels لو Rumble ما كملش ──
    if len(clips) < count:
        still_needed = count - len(clips)
        print(f"🐱 [2/2] Rumble جاب {len(rumble_clips)} — Pexels fallback للباقي ({still_needed})...")
        pexels_clips = _fetch_from_pexels(still_needed, clip_duration)
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
