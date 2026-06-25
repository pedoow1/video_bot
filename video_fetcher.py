# video_fetcher.py - جلب مقاطع قطط مضحكة من Reddit
# يستخدم Reddit RSS (لا يتحجب) + ffmpeg لتقطيع المقاطع

import os
import re
import random
import subprocess
import json
import time
import xml.etree.ElementTree as ET
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 9.0

SUBREDDITS = [
    "cats",
    "catvideos",
    "CatsBeingCats",
    "CatsAreAssholes",
    "AnimalsBeingFunny",
    "aww",
    "funnyanimals",
    "IllegallySmolCats",
]

# User-Agent يشبه المتصفح الحقيقي
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ─── جلب الروابط من Reddit RSS ───────────────────────────────────────────────

def _fetch_via_rss(subreddit: str, sort: str = "hot") -> list:
    """
    يجيب روابط الفيديو عبر Reddit RSS feed.
    RSS مش بيتحجب حتى من السيرفرات السحابية.
    """
    url = f"https://www.reddit.com/r/{subreddit}/{sort}/.rss?limit=25"
    try:
        resp = SESSION.get(url, timeout=20)
        resp.raise_for_status()

        # parse RSS/Atom XML
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        videos = []
        for entry in root.findall("atom:entry", ns):
            link_el = entry.find("atom:link", ns)
            if link_el is None:
                continue
            post_url = link_el.get("href", "")
            if not post_url or "/comments/" not in post_url:
                continue

            title_el = entry.find("atom:title", ns)
            title = title_el.text if title_el is not None else ""

            # نستخرج post ID من الرابط
            m = re.search(r"/comments/([a-z0-9]+)/", post_url)
            if not m:
                continue
            post_id = m.group(1)

            # نجيب JSON المنشور بشكل مباشر
            video_url = _get_video_from_post(post_url, post_id)
            if video_url:
                videos.append({
                    "url":   video_url,
                    "title": title,
                    "id":    post_id,
                })

        return videos

    except Exception as e:
        print(f"  ⚠️ RSS r/{subreddit} فشل: {e}")
        return []


def _get_video_from_post(post_url: str, post_id: str) -> str | None:
    """
    يفتح صفحة JSON للـ post ويستخرج رابط الفيديو.
    Reddit بيسمح بـ .json على المنشورات الفردية.
    """
    try:
        json_url = post_url.rstrip("/") + ".json?limit=1"
        time.sleep(0.4)  # تأخير بسيط بين الطلبات
        resp = SESSION.get(json_url, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        post_data = data[0]["data"]["children"][0]["data"]
        return _extract_video_url(post_data)

    except Exception:
        return None


def _extract_video_url(post: dict) -> str | None:
    """يستخرج direct video URL من بيانات Reddit post."""
    # 1) Reddit-hosted video (v.redd.it)
    if post.get("is_video") and post.get("media"):
        rv = post["media"].get("reddit_video", {})
        url = rv.get("fallback_url") or rv.get("dash_url", "")
        if url:
            return url.split("?")[0]

    url = post.get("url", "")

    # 2) gifv (Imgur)
    if url.endswith(".gifv"):
        return url.replace(".gifv", ".mp4")

    # 3) mp4 مباشر
    if url.endswith(".mp4"):
        return url

    # 4) secure_media fallback
    secure = post.get("secure_media") or {}
    if secure.get("reddit_video"):
        fu = secure["reddit_video"].get("fallback_url", "")
        if fu:
            return fu.split("?")[0]

    return None


# ─── تحميل وتقطيع الكليب ─────────────────────────────────────────────────────

def _download_and_cut(video_url: str, post_id: str, duration: float, out_path: str) -> bool:
    tmp_v = os.path.join(CLIPS_DIR, f"_tmp_{post_id}_v.mp4")
    tmp_a = os.path.join(CLIPS_DIR, f"_tmp_{post_id}_a.mp4")
    tmp_m = os.path.join(CLIPS_DIR, f"_tmp_{post_id}_m.mp4")

    try:
        if not _dl(video_url, tmp_v):
            return False

        # صوت منفصل على v.redd.it
        audio_url = _reddit_audio_url(video_url)
        has_audio = bool(audio_url and _dl(audio_url, tmp_a, silent=True))

        vid_dur = _get_duration(tmp_v)
        if not vid_dur or vid_dur < CLIP_MIN_DURATION:
            return False

        duration = min(duration, vid_dur)
        max_start = max(0.0, vid_dur - duration)
        start = random.uniform(max_start * 0.2, max_start * 0.8) if max_start > 0 else 0.0

        # دمج الصوت لو موجود
        if has_audio and os.path.exists(tmp_a):
            cmd_m = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", tmp_v, "-i", tmp_a,
                "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                "-shortest", tmp_m,
            ]
            subprocess.run(cmd_m, capture_output=True, timeout=60)
            source = tmp_m if os.path.exists(tmp_m) else tmp_v
        else:
            source = tmp_v

        # تقطيع + تحويل لـ 1080p
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", str(round(start, 2)),
            "-i", source,
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
        r = subprocess.run(cmd, capture_output=True, timeout=90)
        if r.returncode != 0:
            print(f"    ⚠️ ffmpeg: {r.stderr.decode()[:150]}")
            return False

        return os.path.exists(out_path) and os.path.getsize(out_path) > 10_000

    except Exception as e:
        print(f"    ⚠️ فشل: {e}")
        return False
    finally:
        for f in [tmp_v, tmp_a, tmp_m]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except OSError:
                pass


def _dl(url: str, path: str, silent: bool = False) -> bool:
    try:
        r = SESSION.get(url, timeout=30, stream=True)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        return os.path.exists(path) and os.path.getsize(path) > 1000
    except Exception as e:
        if not silent:
            print(f"    ⚠️ download ({url[:55]}): {e}")
        return False


def _reddit_audio_url(video_url: str) -> str | None:
    if "v.redd.it" not in video_url:
        return None
    base = re.sub(r"/DASH_[^/?]+$", "", video_url)
    return f"{base}/DASH_audio.mp4" if base != video_url else None


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


# ─── الدالة الرئيسية ─────────────────────────────────────────────────────────

def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    تجيب `count` مقطع من Reddit عبر RSS (لا يتحجب).
    يرجع list من مسارات mp4.
    """
    os.makedirs(CLIPS_DIR, exist_ok=True)

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين — مش محتاج تحميل جديد")
        return random.sample(existing, count)

    print(f"🐱 جاري جلب {count} مقطع من Reddit (RSS)...")

    clips = list(existing)
    needed = count - len(clips)

    # جمّع الفيديوهات من السبريدتات
    all_videos = []
    subs = random.sample(SUBREDDITS, min(len(SUBREDDITS), 4))
    for sub in subs:
        if len(all_videos) >= needed * 4:
            break
        print(f"  📡 r/{sub} ...")
        sort = random.choice(["hot", "top", "new"])
        videos = _fetch_via_rss(sub, sort)
        print(f"     → {len(videos)} فيديو")
        all_videos.extend(videos)
        time.sleep(1)

    if not all_videos:
        print("  ⚠️ مفيش فيديوهات — هنرجع الموجودين")
        return clips[:count] if clips else []

    random.shuffle(all_videos)
    print(f"  📦 {len(all_videos)} فيديو متاح — هنحمّل {needed}")

    for video in all_videos:
        if len(clips) >= count:
            break

        post_id  = video["id"]
        duration = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
        clip_path = os.path.join(CLIPS_DIR, f"reddit_{post_id}.mp4")

        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append(clip_path)
            continue

        print(f"  ⬇️ [{len(clips)+1}/{count}] {video['title'][:55]}...")
        ok = _download_and_cut(video["url"], post_id, duration, clip_path)

        if ok:
            print(f"  ✅ جاهز ({os.path.getsize(clip_path)//1024} KB)")
            clips.append(clip_path)
        else:
            print(f"  ⚠️ فشل — هنجرب التالي")

        time.sleep(0.5)

    # كمّل بالموجودين لو مكملناش العدد
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
    print("🧪 اختبار Reddit RSS fetcher...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ النتيجة:")
    for c in clips:
        sz = os.path.getsize(c) // 1024 if os.path.exists(c) else 0
        print(f"  - {os.path.basename(c)} ({sz} KB)")
