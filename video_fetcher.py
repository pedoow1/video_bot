# video_fetcher.py - جلب مقاطع قطط مضحكة من Reddit
# بيستخدم Reddit JSON API (بدون أي key) + ffmpeg لتقطيع وتحويل المقاطع

import os
import re
import random
import subprocess
import json
import time
import requests
from pathlib import Path
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

# مدة المقطع الواحد بالثواني
CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 9.0

# السبريدتات اللي فيها مقاطع قطط — محتوى لا نهائي ومجاني
SUBREDDITS = [
    "cats",
    "catvideos",
    "CatsBeingCats",
    "IllegallySmolCats",
    "AnimalsBeingFunny",
    "aww",
    "CatsAreAssholes",
    "funnyanimals",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; CatVideoBot/1.0; +https://github.com/catbot)",
    "Accept": "application/json",
}


# ─── جلب الروابط من Reddit ───────────────────────────────────────────────────

def _fetch_reddit_videos(subreddit: str, limit: int = 25, sort: str = "hot") -> list:
    """
    يجيب روابط الفيديو من subreddit معين عبر Reddit JSON API (بدون key).
    sort: hot | new | top | rising
    """
    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json?limit={limit}&t=week"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", {}).get("children", [])

        videos = []
        for post in posts:
            p = post.get("data", {})
            video_url = _extract_video_url(p)
            if not video_url:
                continue
            videos.append({
                "url":       video_url,
                "title":     p.get("title", "")[:80],
                "id":        p.get("id", ""),
                "subreddit": subreddit,
            })

        return videos

    except Exception as e:
        print(f"  ⚠️ Reddit r/{subreddit} فشل: {e}")
        return []


def _extract_video_url(post: dict) -> str | None:
    """
    يستخرج direct video URL من بيانات Reddit post.
    يدعم: reddit-hosted videos (v.redd.it) و gifv و gif و mp4 خارجي.
    """
    # 1) Reddit-hosted video (v.redd.it)
    if post.get("is_video") and post.get("media"):
        reddit_video = post["media"].get("reddit_video", {})
        url = reddit_video.get("fallback_url") or reddit_video.get("dash_url")
        if url:
            # نزيل ?source=fallback لو موجودة لأنها مش ضرورية
            return url.split("?")[0]

    # 2) gifv (Imgur)
    url = post.get("url", "")
    if url.endswith(".gifv"):
        return url.replace(".gifv", ".mp4")

    # 3) mp4 مباشر
    if url.endswith(".mp4"):
        return url

    # 4) gif (ffmpeg بيتعامل معاه عادي)
    if url.endswith(".gif") and "imgur" in url:
        return url

    # 5) secure_media fallback
    secure = post.get("secure_media", {})
    if secure and secure.get("reddit_video"):
        url = secure["reddit_video"].get("fallback_url", "")
        if url:
            return url.split("?")[0]

    return None


# ─── تحميل وتقطيع المقطع ─────────────────────────────────────────────────────

def _download_and_cut(video_url: str, post_id: str, duration: float, out_path: str) -> bool:
    """
    يحمّل فيديو Reddit ويقطع منه مقطع بالمدة المطلوبة.
    Reddit videos عادةً قصيرة (10-60 ثانية)، فبنبدأ من نص الفيديو.
    """
    tmp_video = os.path.join(CLIPS_DIR, f"_tmp_{post_id}_v.mp4")
    tmp_audio = os.path.join(CLIPS_DIR, f"_tmp_{post_id}_a.mp4")
    tmp_merged = os.path.join(CLIPS_DIR, f"_tmp_{post_id}_m.mp4")

    try:
        # ─ تحميل الفيديو ─
        if not _download_file(video_url, tmp_video):
            return False

        # ─ تحميل الصوت (Reddit يفصل الصوت في ملف منفصل أحيانًا) ─
        audio_url = _get_reddit_audio_url(video_url)
        has_audio = False
        if audio_url:
            has_audio = _download_file(audio_url, tmp_audio, silent=True)

        # ─ احسب نقطة البداية ─
        vid_duration = _get_duration(tmp_video)
        if vid_duration is None or vid_duration < CLIP_MIN_DURATION:
            return False

        duration = min(duration, vid_duration)
        max_start = max(0.0, vid_duration - duration)
        start = random.uniform(max_start * 0.2, max_start * 0.8) if max_start > 0 else 0.0

        # ─ دمج الفيديو والصوت أو مجرد قطع ─
        if has_audio and os.path.exists(tmp_audio):
            _merge_video_audio(tmp_video, tmp_audio, tmp_merged)
            source = tmp_merged if os.path.exists(tmp_merged) else tmp_video
        else:
            source = tmp_video

        # ─ تقطيع + تحويل لـ 1080p ─
        cmd = [
            "ffmpeg", "-y",
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
            "-loglevel", "error",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=90)

        if result.returncode != 0:
            print(f"    ⚠️ ffmpeg error: {result.stderr.decode()[:200]}")
            return False

        return os.path.exists(out_path) and os.path.getsize(out_path) > 10_000

    except Exception as e:
        print(f"    ⚠️ download/cut فشل: {e}")
        return False

    finally:
        for f in [tmp_video, tmp_audio, tmp_merged]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass


def _download_file(url: str, path: str, silent: bool = False) -> bool:
    """يحمّل ملف عبر requests."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return os.path.exists(path) and os.path.getsize(path) > 1000
    except Exception as e:
        if not silent:
            print(f"    ⚠️ download فشل ({url[:60]}): {e}")
        return False


def _get_reddit_audio_url(video_url: str) -> str | None:
    """
    Reddit بيحط الصوت في ملف منفصل على v.redd.it.
    مثال: https://v.redd.it/XXXX/DASH_720.mp4
         → https://v.redd.it/XXXX/DASH_audio.mp4
    """
    if "v.redd.it" not in video_url:
        return None
    base = re.sub(r"/DASH_[^/]+\.mp4$", "", video_url)
    if not base or base == video_url:
        return None
    return f"{base}/DASH_audio.mp4"


def _merge_video_audio(video_path: str, audio_path: str, out_path: str):
    """يدمج فيديو وصوت في ملف واحد."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-loglevel", "error",
        out_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=60)


def _get_duration(path: str) -> float | None:
    """يجيب مدة الفيديو بالثواني."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return None


# ─── الدالة الرئيسية ─────────────────────────────────────────────────────────

def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    الدالة الرئيسية — تجيب `count` مقطع من قطط مضحكة من Reddit.
    يرجع list من مسارات ملفات mp4.

    count:         عدد المقاطع المطلوبة
    clip_duration: مدة كل مقطع بالثواني (None = عشوائي)
    """
    os.makedirs(CLIPS_DIR, exist_ok=True)

    # لو عندنا كليبات محملة بالفعل — استخدمها
    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين بالفعل — مش محتاج تحميل جديد")
        return random.sample(existing, count)

    print(f"🐱 جاري جلب {count} مقطع قطط من Reddit...")

    clips = list(existing)
    needed = count - len(clips)

    # اجمع كل الفيديوهات من السبريدتات المختلفة
    all_videos = []
    subs_to_use = random.sample(SUBREDDITS, min(len(SUBREDDITS), 4))

    for sub in subs_to_use:
        print(f"  📡 r/{sub} ...")
        sort = random.choice(["hot", "top", "new"])
        videos = _fetch_reddit_videos(sub, limit=25, sort=sort)
        all_videos.extend(videos)
        if len(all_videos) >= needed * 3:
            break
        time.sleep(0.5)  # لا نضغط على Reddit API

    if not all_videos:
        print("  ⚠️ مفيش فيديوهات من Reddit — هنرجع كليبات موجودة")
        return clips[:count] if clips else []

    random.shuffle(all_videos)
    print(f"  ✅ لقينا {len(all_videos)} فيديو — هنحمّل منهم {needed}")

    for video in all_videos:
        if len(clips) >= count:
            break

        post_id = video["id"]
        title   = video["title"]
        url     = video["url"]
        duration = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)

        clip_name = f"reddit_{post_id}.mp4"
        clip_path = os.path.join(CLIPS_DIR, clip_name)

        # لو الكليب موجود بالفعل
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            print(f"  ✅ كليب موجود: {clip_name}")
            clips.append(clip_path)
            continue

        print(f"  ⬇️ [{len(clips)+1}/{count}] {title[:55]}...")

        success = _download_and_cut(url, post_id, duration, clip_path)

        if success:
            size_kb = os.path.getsize(clip_path) // 1024
            print(f"  ✅ جاهز ({size_kb} KB)")
            clips.append(clip_path)
        else:
            print(f"  ⚠️ فشل — هنجرب التالي")

        time.sleep(0.3)

    # لو مش وصلنا العدد المطلوب — نكرر الموجودين
    if len(clips) < count:
        print(f"  ⚠️ جبنا {len(clips)} من {count} — هنكرر الموجودين")
        while len(clips) < count and clips:
            clips.append(random.choice(clips))

    result = clips[:count]
    print(f"✅ {len(result)} مقطع جاهز!")
    return result


# ─── مساعدات ─────────────────────────────────────────────────────────────────

def _get_existing_clips(limit: int = None) -> list:
    """يجيب الكليبات المحملة بالفعل في CLIPS_DIR."""
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = [
        os.path.join(CLIPS_DIR, f)
        for f in os.listdir(CLIPS_DIR)
        if f.endswith(".mp4")
        and not f.startswith("_tmp")
        and os.path.getsize(os.path.join(CLIPS_DIR, f)) > 10_000
    ]
    random.shuffle(clips)
    return clips[:limit] if limit else clips


def clear_clips_cache():
    """يمسح الكليبات المحملة عشان يجيب جديدة في المرة الجاية."""
    if not os.path.exists(CLIPS_DIR):
        return
    removed = 0
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4"):
            try:
                os.remove(os.path.join(CLIPS_DIR, f))
                removed += 1
            except OSError:
                pass
    print(f"🗑️ تم مسح {removed} كليب")


# ─── اختبار مستقل ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 اختبار video_fetcher (Reddit)...\n")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ الكليبات ({len(clips)}):")
    for c in clips:
        size = os.path.getsize(c) // 1024 if os.path.exists(c) else 0
        print(f"  - {os.path.basename(c)} ({size} KB)")
