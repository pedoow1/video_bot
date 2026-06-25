# video_fetcher.py - جلب مقاطع قطط مضحكة من Rumble
# yt-dlp بيشتغل مع Rumble بدون أي blocking من GitHub Actions

import os
import re
import random
import subprocess
import json
import time
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 15.0  # max 15 ثانية

# search queries على Rumble
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


def _ensure_ytdlp():
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("📦 تثبيت yt-dlp...")
        subprocess.run(["pip", "install", "yt-dlp", "-q", "--break-system-packages"], check=True)

    # curl_cffi مطلوب لـ --impersonate (تجاوز Cloudflare بدون cookies)
    try:
        import curl_cffi  # noqa
    except ImportError:
        print("📦 تثبيت curl_cffi (مطلوب لـ Rumble)...")
        subprocess.run(
            ["pip", "install", "curl_cffi>=0.10,<0.15", "-q", "--break-system-packages"],
            check=True
        )


def _search_rumble(query: str, limit: int = 15) -> list:
    """يبحث على Rumble عبر yt-dlp مباشرة."""
    print(f"  🔍 Rumble: {query}")
    try:
        # rumble:QUERY هو الطريقة الصح مع yt-dlp للبحث على Rumble
        # --impersonate chrome:android بيخلي yt-dlp يتصرف كموبايل Chrome
        # وبيعمل TLS fingerprint حقيقي يتجاوز Cloudflare بدون cookies
        search_url = f"rumble:{query}"
        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-end", str(limit),
            "--dump-json",
            "--no-warnings",
            "--quiet",
            "--impersonate", "chrome:android",
            search_url,
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
                if not url:
                    continue
                # نتجاهل فيديوهات أطول من دقيقتين — غالباً compilations
                if duration > 120:
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
        print(f"  ⚠️ بحث فشل ({query}): {e}")
        return []


def _download_clip(video_url: str, post_id: str, target_duration: float, out_path: str) -> bool:
    """يحمّل فيديو من Rumble ويقطع منه مقطع بالمدة المطلوبة (max 15s)."""
    tmp = os.path.join(CLIPS_DIR, f"_tmp_{post_id}.mp4")
    try:
        # تحميل بـ yt-dlp مع impersonate لتجاوز Cloudflare
        cmd_dl = [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]/best",
            "--merge-output-format", "mp4",
            "--impersonate", "chrome:android",
            "-o", tmp,
            "--no-warnings",
            "--quiet",
            video_url,
        ]
        r = subprocess.run(cmd_dl, capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.exists(tmp):
            # fallback بدون format selector
            subprocess.run(
                ["yt-dlp", "-f", "best", "--impersonate", "chrome:android",
                 "-o", tmp, "--no-warnings", "--quiet", video_url],
                capture_output=True, timeout=90
            )

        if not os.path.exists(tmp) or os.path.getsize(tmp) < 5000:
            return False

        # مدة الفيديو الفعلية
        vid_dur = _get_duration(tmp)
        if not vid_dur or vid_dur < CLIP_MIN_DURATION:
            return False

        # نقطع بحد أقصى 15 ثانية
        cut_dur = min(target_duration, vid_dur, CLIP_MAX_DURATION)
        max_start = max(0.0, vid_dur - cut_dur)
        start = random.uniform(0, max_start) if max_start > 0 else 0.0

        cmd_cut = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(round(start, 2)),
            "-i", tmp,
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
        r2 = subprocess.run(cmd_cut, capture_output=True, timeout=90)
        if r2.returncode != 0:
            print(f"    ⚠️ ffmpeg: {r2.stderr.decode()[:120]}")
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
    تجيب `count` مقطع قطط مضحكة من Rumble.
    كل مقطع بحد أقصى 15 ثانية.
    """
    _ensure_ytdlp()
    os.makedirs(CLIPS_DIR, exist_ok=True)

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين — مش محتاج تحميل")
        return random.sample(existing, count)

    print(f"🐱 جاري جلب {count} مقطع من Rumble (max 15s لكل واحد)...")

    clips = list(existing)
    needed = count - len(clips)

    # جمّع فيديوهات من queries مختلفة
    all_videos = []
    queries = random.sample(SEARCH_QUERIES, min(len(SEARCH_QUERIES), 4))
    for q in queries:
        if len(all_videos) >= needed * 4:
            break
        vids = _search_rumble(q, limit=15)
        all_videos.extend(vids)
        time.sleep(1)

    if not all_videos:
        print("  ⚠️ مفيش فيديوهات — هنرجع الموجودين")
        return clips

    # إزالة التكرار
    seen = set()
    unique_videos = []
    for v in all_videos:
        if v["id"] not in seen:
            seen.add(v["id"])
            unique_videos.append(v)

    random.shuffle(unique_videos)
    print(f"  📦 {len(unique_videos)} فيديو — هنحمّل {needed}")

    for video in unique_videos:
        if len(clips) >= count:
            break

        post_id  = video["id"]
        duration = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
        clip_path = os.path.join(CLIPS_DIR, f"rumble_{post_id}.mp4")

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append(clip_path)
            continue

        print(f"  ⬇️ [{len(clips)+1}/{count}] {video['title'][:55]}...")
        ok = _download_clip(video["url"], post_id, duration, clip_path)

        if ok:
            sz = os.path.getsize(clip_path) // 1024
            print(f"  ✅ جاهز ({sz} KB)")
            clips.append(clip_path)
        else:
            print(f"  ⚠️ فشل — التالي")

        time.sleep(0.5)

    # كمّل بالموجودين لو مكملناش
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
    print("🧪 اختبار Rumble fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c) // 1024 if os.path.exists(c) else 0
        print(f"  - {os.path.basename(c)} ({sz} KB)")
