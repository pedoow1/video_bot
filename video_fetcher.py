# video_fetcher.py - جلب مقاطع قطط مضحكة
# يستخدم yt-dlp على Reddit (يتجاوز الـ 403/429 تلقائيًا)

import os
import re
import random
import subprocess
import json
import time
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 9.0

# URLs مباشرة لـ Reddit subreddits — yt-dlp بيفهمها
SUBREDDIT_URLS = [
    "https://www.reddit.com/r/catvideos/",
    "https://www.reddit.com/r/cats/",
    "https://www.reddit.com/r/CatsBeingCats/",
    "https://www.reddit.com/r/CatsAreAssholes/",
    "https://www.reddit.com/r/AnimalsBeingFunny/",
    "https://www.reddit.com/r/aww/",
    "https://www.reddit.com/r/funnyanimals/",
]


def _ensure_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("📦 تثبيت yt-dlp...")
        subprocess.run(
            ["pip", "install", "yt-dlp", "-q", "--break-system-packages"],
            check=True
        )


def _get_reddit_video_urls(subreddit_url: str, limit: int = 15) -> list:
    """
    يستخدم yt-dlp لجلب قائمة الفيديوهات من subreddit.
    yt-dlp بيتعامل مع Reddit API بشكل صحيح ويتجاوز الـ blocking.
    """
    print(f"  📡 {subreddit_url.split('r/')[1].rstrip('/')} ...")
    try:
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end", str(limit),
            "--dump-json",
            "--no-warnings",
            "--quiet",
            # Reddit-specific: جرب بدون login أولًا
            "--extractor-args", "reddit:max_comments=0",
            subreddit_url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        videos = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                info = json.loads(line)
                url = info.get("url") or info.get("webpage_url", "")
                vid_id = info.get("id", url[-8:] if url else "")
                title = info.get("title", "")
                if url and ("reddit" in url or "v.redd.it" in url):
                    videos.append({"url": url, "id": vid_id, "title": title})
            except json.JSONDecodeError:
                continue

        print(f"     → {len(videos)} فيديو")
        return videos

    except Exception as e:
        print(f"  ⚠️ فشل: {e}")
        return []


def _download_clip(video_url: str, post_id: str, duration: float, out_path: str) -> bool:
    """
    يحمّل فيديو Reddit بـ yt-dlp ويقطعه بـ ffmpeg.
    """
    tmp = os.path.join(CLIPS_DIR, f"_tmp_{post_id}.mp4")
    try:
        # تحميل بـ yt-dlp
        cmd_dl = [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "--merge-output-format", "mp4",
            "-o", tmp,
            "--no-warnings",
            "--quiet",
            video_url,
        ]
        result = subprocess.run(cmd_dl, capture_output=True, timeout=120)
        if result.returncode != 0 or not os.path.exists(tmp):
            # جرب بدون format selector
            cmd_dl2 = [
                "yt-dlp", "-f", "best",
                "-o", tmp, "--no-warnings", "--quiet", video_url
            ]
            subprocess.run(cmd_dl2, capture_output=True, timeout=90)

        if not os.path.exists(tmp) or os.path.getsize(tmp) < 5000:
            return False

        # احسب مدة الفيديو
        vid_dur = _get_duration(tmp)
        if not vid_dur or vid_dur < CLIP_MIN_DURATION:
            return False

        duration = min(duration, vid_dur)
        max_start = max(0.0, vid_dur - duration)
        start = random.uniform(max_start * 0.15, max_start * 0.85) if max_start > 0 else 0.0

        # تقطيع + تحويل لـ 1080p
        cmd_cut = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(round(start, 2)),
            "-i", tmp,
            "-t", str(round(duration, 2)),
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
        r = subprocess.run(cmd_cut, capture_output=True, timeout=90)
        if r.returncode != 0:
            print(f"    ⚠️ ffmpeg: {r.stderr.decode()[:120]}")
            return False

        return os.path.exists(out_path) and os.path.getsize(out_path) > 10_000

    except Exception as e:
        print(f"    ⚠️ فشل: {e}")
        return False
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _get_duration(path: str) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=15
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return None


def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    الدالة الرئيسية — تجيب `count` مقطع من Reddit عبر yt-dlp.
    """
    _ensure_ytdlp()
    os.makedirs(CLIPS_DIR, exist_ok=True)

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين — مش محتاج تحميل")
        return random.sample(existing, count)

    print(f"🐱 جاري جلب {count} مقطع من Reddit...")

    clips = list(existing)
    needed = count - len(clips)

    # جمّع الفيديوهات من سبريدتات مختلفة
    all_videos = []
    subs = random.sample(SUBREDDIT_URLS, min(len(SUBREDDIT_URLS), 3))
    for sub_url in subs:
        if len(all_videos) >= needed * 3:
            break
        videos = _get_reddit_video_urls(sub_url, limit=20)
        all_videos.extend(videos)
        time.sleep(1)

    if not all_videos:
        print("  ⚠️ مفيش فيديوهات — هنرجع الموجودين")
        return clips[:count] if clips else []

    random.shuffle(all_videos)
    print(f"  📦 {len(all_videos)} فيديو — هنحمّل {needed}")

    for video in all_videos:
        if len(clips) >= count:
            break

        post_id = re.sub(r"[^a-zA-Z0-9]", "_", video["id"])[:20]
        duration = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
        clip_path = os.path.join(CLIPS_DIR, f"reddit_{post_id}.mp4")

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append(clip_path)
            continue

        print(f"  ⬇️ [{len(clips)+1}/{count}] {video['title'][:55]}...")
        ok = _download_clip(video["url"], post_id, duration, clip_path)

        if ok:
            print(f"  ✅ جاهز ({os.path.getsize(clip_path)//1024} KB)")
            clips.append(clip_path)
        else:
            print(f"  ⚠️ فشل — التالي")

        time.sleep(0.5)

    if len(clips) < count and clips:
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
    n = sum(
        1 for f in os.listdir(CLIPS_DIR)
        if f.endswith(".mp4") and not os.remove(os.path.join(CLIPS_DIR, f))
    )
    print(f"🗑️ مسح {n} كليب")


if __name__ == "__main__":
    print("🧪 اختبار Reddit yt-dlp fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ النتيجة ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c) // 1024 if os.path.exists(c) else 0
        print(f"  - {os.path.basename(c)} ({sz} KB)")
