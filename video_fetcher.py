# video_fetcher.py - جلب مقاطع قطط مضحكة من يوتيوب (Creative Commons)
# يستخدم yt-dlp للبحث والتحميل، وffmpeg لتقطيع المقاطع

import os
import random
import subprocess
import json
import time
from pathlib import Path
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

# مدة المقطع الواحد بالثواني
CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 9.0

# كلمات البحث على يوتيوب - Creative Commons فقط
SEARCH_QUERIES = [
    "funny cats compilation",
    "cute cats funny moments",
    "cats being silly",
    "funny kittens",
    "cats fail compilation",
    "cats vs cucumbers funny",
    "cats jumping failing",
    "cute funny cats",
    "cats playing funny",
    "hilarious cat moments",
    "cat doing funny things",
    "cats scared funny",
]


def _install_ytdlp():
    """يثبت yt-dlp لو مش موجود"""
    try:
        subprocess.run(["yt-dlp", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("📦 جاري تثبيت yt-dlp...")
        subprocess.run(
            ["pip", "install", "yt-dlp", "-q", "--break-system-packages"],
            check=True
        )
        print("✅ yt-dlp اتثبت")


def _search_youtube_cc(query: str, max_results: int = 10) -> list:
    """
    يبحث على يوتيوب عن فيديوهات Creative Commons.
    يرجع list من dicts فيها url, title, duration.
    """
    print(f"  🔍 بيبحث: {query}")
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{max_results}:{query}",
            "--dump-json",
            "--no-download",
            "--quiet",
            "--no-warnings",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        videos = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                info = json.loads(line)
                duration = info.get("duration", 0) or 0
                license_info = info.get("license") or ""

                # نقبل فيديو لو:
                # 1. license فيها "Creative Commons" صراحةً
                # 2. أو مفيش license ونثق في الـ query إن النتائج مناسبة
                is_cc = "creative commons" in license_info.lower()

                if 30 <= duration <= 900:
                    videos.append({
                        "url":      info.get("webpage_url") or info.get("url"),
                        "title":    info.get("title", ""),
                        "duration": duration,
                        "id":       info.get("id", ""),
                        "is_cc":    is_cc,
                    })
            except json.JSONDecodeError:
                continue

        # نفضل CC أولاً، لو مفيش ناخد أي نتيجة
        cc_videos = [v for v in videos if v["is_cc"]]
        final = cc_videos if cc_videos else videos

        print(f"  ✅ لقى {len(final)} فيديو (CC: {len(cc_videos)}, total: {len(videos)})")
        return final

    except subprocess.TimeoutExpired:
        print("  ⚠️ البحث استغرق وقت طويل — تخطي")
        return []
    except Exception as e:
        print(f"  ⚠️ خطأ في البحث: {e}")
        return []


def _download_video_segment(url: str, video_id: str, start: float, duration: float, out_path: str) -> bool:
    """
    يحمّل جزء معين من الفيديو مباشرةً بـ yt-dlp + ffmpeg.
    أسرع بكتير من تحميل الفيديو كامل.
    """
    try:
        # أول خطوة: جيب الـ direct stream URL
        cmd_url = [
            "yt-dlp",
            "-f", "best[height<=720][ext=mp4]/best[height<=720]/best",
            "--get-url",
            "--quiet",
            "--no-warnings",
            url,
        ]
        result = subprocess.run(cmd_url, capture_output=True, text=True, timeout=30)
        stream_url = result.stdout.strip()

        if not stream_url or "ERROR" in stream_url:
            # fallback: تحميل الفيديو كامل وتقطيعه
            return _download_full_then_cut(url, video_id, start, duration, out_path)

        # تقطيع مباشر من الـ stream بـ ffmpeg
        cmd_ffmpeg = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", stream_url,
            "-t", str(duration),
            "-vf", f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            out_path,
        ]
        subprocess.run(cmd_ffmpeg, capture_output=True, timeout=120, check=True)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 10_000:
            return True
        return False

    except Exception as e:
        print(f"    ⚠️ stream download فشل: {e}")
        return _download_full_then_cut(url, video_id, start, duration, out_path)


def _download_full_then_cut(url: str, video_id: str, start: float, duration: float, out_path: str) -> bool:
    """
    Fallback: يحمّل الفيديو كامل ثم يقطع منه الجزء المطلوب.
    """
    tmp_path = os.path.join(CLIPS_DIR, f"_tmp_{video_id}.mp4")
    try:
        # تحميل بجودة متوسطة عشان يكون أسرع
        cmd_dl = [
            "yt-dlp",
            "-f", "best[height<=480][ext=mp4]/best[height<=480]/worst",
            "-o", tmp_path,
            "--quiet",
            "--no-warnings",
            url,
        ]
        subprocess.run(cmd_dl, capture_output=True, timeout=180, check=True)

        if not os.path.exists(tmp_path):
            return False

        # تقطيع
        cmd_cut = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", tmp_path,
            "-t", str(duration),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            out_path,
        ]
        subprocess.run(cmd_cut, capture_output=True, timeout=60, check=True)

        return os.path.exists(out_path) and os.path.getsize(out_path) > 10_000

    except Exception as e:
        print(f"    ⚠️ full download فشل: {e}")
        return False
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def fetch_cat_clips(count: int, clip_duration: float = None) -> list:
    """
    الدالة الرئيسية — تجيب `count` مقطع من قطط مضحكة.
    يرجع list من مسارات ملفات الفيديو.

    count: عدد المقاطع المطلوبة (= عدد الفقرات في السكريبت)
    clip_duration: مدة كل مقطع بالثواني (None = عشوائي بين MIN و MAX)
    """
    _install_ytdlp()
    os.makedirs(CLIPS_DIR, exist_ok=True)

    # لو عندنا كليبات محملة بالفعل — استخدمها مباشرة
    existing = _get_existing_clips(count)
    if len(existing) >= count:
        print(f"✅ {count} كليب موجودين بالفعل — مش محتاج تحميل جديد")
        return random.sample(existing, count)

    print(f"🎬 جاري جلب {count} مقطع قطط Creative Commons من يوتيوب...")

    clips = list(existing)  # ابدأ بالموجودين
    needed = count - len(clips)

    # خلط الـ queries عشان نتنوع
    queries = random.sample(SEARCH_QUERIES, min(len(SEARCH_QUERIES), needed + 2))

    for query in queries:
        if len(clips) >= count:
            break

        videos = _search_youtube_cc(query, max_results=8)
        if not videos:
            continue

        random.shuffle(videos)

        for video in videos:
            if len(clips) >= count:
                break

            vid_id   = video["id"]
            vid_dur  = video["duration"]
            vid_url  = video["url"]

            # نختار نقطة عشوائية في منتصف الفيديو (نتجنب الأول والآخر)
            margin   = min(10.0, vid_dur * 0.1)
            max_start = max(0, vid_dur - CLIP_MAX_DURATION - margin)
            start    = random.uniform(margin, max(margin, max_start))
            duration = clip_duration or random.uniform(CLIP_MIN_DURATION, CLIP_MAX_DURATION)
            duration = min(duration, vid_dur - start)

            if duration < CLIP_MIN_DURATION:
                continue

            # اسم الملف
            clip_name = f"cat_{vid_id}_{int(start)}.mp4"
            clip_path = os.path.join(CLIPS_DIR, clip_name)

            if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
                print(f"  ✅ كليب موجود: {clip_name}")
                clips.append(clip_path)
                continue

            print(f"  ⬇️ بيحمّل: {video['title'][:50]}... ({start:.0f}s → {start+duration:.0f}s)")

            success = _download_video_segment(vid_url, vid_id, start, duration, clip_path)

            if success:
                print(f"  ✅ كليب {len(clips)+1}/{count} جاهز")
                clips.append(clip_path)
                time.sleep(1)  # عشان مانضغطش على يوتيوب
            else:
                print(f"  ⚠️ فشل تحميل: {video['title'][:40]}")

    if len(clips) < count:
        print(f"  ⚠️ جبنا {len(clips)} من {count} — هنكرر الموجودين")
        while len(clips) < count:
            clips.append(random.choice(clips))

    result = clips[:count]
    print(f"✅ {len(result)} مقطع قطط جاهز!")
    return result


def _get_existing_clips(limit: int = None) -> list:
    """يجيب الكليبات المحملة بالفعل"""
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = [
        os.path.join(CLIPS_DIR, f)
        for f in os.listdir(CLIPS_DIR)
        if f.endswith(".mp4") and not f.startswith("_tmp")
        and os.path.getsize(os.path.join(CLIPS_DIR, f)) > 10_000
    ]
    random.shuffle(clips)
    return clips[:limit] if limit else clips


def clear_clips_cache():
    """يمسح الكليبات المحملة عشان يجيب جديدة في المرة الجاية"""
    if not os.path.exists(CLIPS_DIR):
        return
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4"):
            try:
                os.remove(os.path.join(CLIPS_DIR, f))
            except OSError:
                pass
    print("🗑️ تم مسح الكليبات القديمة")


if __name__ == "__main__":
    print("🧪 اختبار video_fetcher...")
    clips = fetch_cat_clips(count=3)
    print(f"\n✅ الكليبات:")
    for c in clips:
        print(f"  - {c}")
