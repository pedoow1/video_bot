# video_fetcher.py - GPT-4o بيبحث في archive.org ويجيب روابط mp4 مباشرة

import os
import random
import subprocess
import json
import time
import requests
from config import OUTPUT_DIR, GITHUB_TOKEN

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION  = 4.0
CLIP_MAX_DURATION  = 30.0
TARGET_VIDEO_DURATION = 300

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"
IA_DOWNLOAD_BASE  = "https://archive.org/download"


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
# GPT-4o يبحث في archive.org ويجيب روابط mp4
# ──────────────────────────────────────────

def _ask_gpt_for_direct_urls(count: int) -> list:
    """
    GPT-4o بيستخدم web search يبحث في archive.org
    ويرجع روابط mp4 مباشرة قابلة للتحميل.
    """
    if not GITHUB_TOKEN:
        print("  ⚠️ GH_TOKEN مش موجود")
        return []

    prompt = f"""Search archive.org for {count} funny animal videos and return direct download links.

Use web search to find real .mp4 files on archive.org. Search for:
- "site:archive.org funny cats mp4"
- "site:archive.org funny dogs compilation mp4"
- "site:archive.org funny animals mp4"

For each video found, get the DIRECT mp4 download URL in this format:
https://archive.org/download/IDENTIFIER/filename.mp4

Rules:
- Must be real animals (cats, dogs, birds, pets) — NO cartoons, NO animations
- Must be a direct .mp4 link that can be downloaded
- Must be publicly accessible

Reply with JSON ONLY:
{{
  "videos": [
    {{"url": "https://archive.org/download/IDENTIFIER/file.mp4", "title": "video title"}},
    ...
  ]
}}

Exactly {count} items with real, working direct mp4 URLs."""

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000,
        "temperature": 0.2,
        "tools": [{"type": "web_search_preview"}],
    }

    for attempt in range(3):
        try:
            print(f"  🔍 GPT-4o بيبحث في archive.org (محاولة {attempt+1})...")
            r = requests.post(GITHUB_MODELS_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()

            # استخرج الـ text من الـ response
            content = r.json()["choices"][0]["message"]["content"]
            if not content:
                print(f"  ⚠️ response فاضي")
                continue

            content = content.replace("```json", "").replace("```", "").strip()
            data    = json.loads(content)
            videos  = data.get("videos", [])

            if videos:
                print(f"  ✅ GPT-4o لقى {len(videos)} فيديو:")
                for v in videos:
                    print(f"     • {v['url'][:80]}")
                return videos

        except json.JSONDecodeError:
            print(f"  ⚠️ محاولة {attempt+1}: مش JSON — {content[:200]}")
        except Exception as e:
            print(f"  ⚠️ محاولة {attempt+1} فشلت: {e}")
            time.sleep(3)

    return []


# ──────────────────────────────────────────
# تحميل كليب من رابط مباشر
# ──────────────────────────────────────────

def _download_from_url(url: str, title: str, clip_duration: float) -> dict | None:
    # اسم الملف من الـ URL
    safe_name = url.split("/")[-1].replace(".mp4", "").replace(" ", "_")[:40]
    clip_path = os.path.join(CLIPS_DIR, f"ia_{safe_name}.mp4")
    tmp       = os.path.join(CLIPS_DIR, f"_tmp_{safe_name}.mp4")

    # كاش
    if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
        print(f"  ✅ كاش: {safe_name}")
        return {"path": clip_path, "description": title, "ia_url": url}

    try:
        print(f"  ⬇️ {url[:70]}...")
        r = requests.get(url, stream=True, timeout=120,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            print(f"  ⚠️ فشل: HTTP {r.status_code}")
            return None

        downloaded = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                f.write(chunk)
                downloaded += len(chunk)
                if downloaded > 150_000_000:
                    break

        if not os.path.exists(tmp) or os.path.getsize(tmp) < 500_000:
            print(f"  ⚠️ ملف صغير جداً أو فاضي")
            return None

        if _cut_clip(tmp, clip_path, clip_duration):
            print(f"  ✅ جاهز ({os.path.getsize(clip_path)//1024} KB)")
            return {"path": clip_path, "description": title, "ia_url": url}
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

    # GPT-4o يبحث ويجيب روابط مباشرة
    print(f"\n🤖 GPT-4o بيبحث في archive.org عن {needed} فيديو حيوانات...")
    videos = _ask_gpt_for_direct_urls(needed + 3)

    if not videos:
        print("❌ GPT-4o مرجعش بنتائج")
        return clips

    random.shuffle(videos)

    for video in videos:
        if len(clips) >= count:
            break
        url   = video.get("url", "")
        title = video.get("title", "funny animals")

        if not url or "archive.org" not in url:
            print(f"  ⚠️ رابط مش من archive.org: {url[:60]}")
            continue

        result = _download_from_url(url, title, clip_duration)
        if result:
            clips.append(result)

    # كرر لو ناقص
    if 0 < len(clips) < count:
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
    print("🧪 اختبار...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ ({len(clips)}):")
    for c in clips:
        sz = os.path.getsize(c["path"]) // 1024 if os.path.exists(c["path"]) else 0
        print(f"  - {os.path.basename(c['path'])} ({sz} KB) | {c['description'][:60]}")
