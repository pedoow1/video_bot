# video_fetcher.py
import os
import random
import subprocess
import json
import time
import re
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")
CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 30.0
TARGET_VIDEO_DURATION = 300

YOUTUBE_QUERIES = [
    "funny cats", "cute kittens", "cat fails", "hilarious cats",
    "funny dogs", "cute funny animals", "kittens playing", "funny pets"
]

def _get_duration(path: str) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                           capture_output=True, text=True, timeout=15)
        return float(json.loads(r.stdout)["format"]["duration"])
    except:
        return None

def _cut_clip(src: str, out_path: str, target_duration: float) -> bool:
    vid_dur = _get_duration(src)
    if not vid_dur or vid_dur < CLIP_MIN_DURATION:
        return False
    cut_dur = min(target_duration, vid_dur, CLIP_MAX_DURATION)
    start = random.uniform(0, max(0, vid_dur - cut_dur))

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(round(start, 2)), "-i", src, "-t", str(round(cut_dur, 2)),
           "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
           "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out_path]
    r = subprocess.run(cmd, capture_output=True, timeout=90)
    return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 10_000

def _sanitize_id(video_id: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', video_id)

def _search_with_api(query: str, max_results: int = 10) -> list:
    """بحث بـ YouTube Data API v3"""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("  ⚠️ YOUTUBE_API_KEY مش موجود")
        return []

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "maxResults": max_results,
        "videoDuration": "medium",
        "key": api_key
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        data = r.json()
        videos = []
        for item in data.get("items", []):
            vid_id = item["id"]["videoId"]
            videos.append({
                "id": vid_id,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "title": item["snippet"]["title"],
            })
        print(f"  ✅ API وجد {len(videos)} فيديو لـ {query}")
        return videos
    except Exception as e:
        print(f"  ⚠️ API خطأ: {e}")
        return []

def _download_video(url: str, video_id: str) -> str | None:
    safe_id = _sanitize_id(video_id)
    tmp_path = os.path.join(CLIPS_DIR, f"_tmp_{safe_id}.mp4")

    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
        return tmp_path

    cmd = [
        "yt-dlp", "-f", "bestvideo[ext=mp4][height<=720]+bestaudio/best", "--merge-output-format", "mp4",
        "--no-playlist", "--quiet", "--no-warnings", "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=ios,android,web",
        "-o", tmp_path, url
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 3_000_000:
            print(f"  ✅ تحميل ناجح: {video_id}")
            return tmp_path
        else:
            print(f"  ⚠️ تحميل فشل: {video_id}")
            return None
    except Exception as e:
        print(f"  ⚠️ خطأ تحميل: {e}")
        return None

def _fetch_from_youtube(count: int, clip_duration: float) -> list:
    print(f"  🎬 جاري البحث عن {count} فيديو بـ YouTube API...")
    clips = []
    queries = random.sample(YOUTUBE_QUERIES, min(6, len(YOUTUBE_QUERIES)))
    all_videos = []

    for q in queries:
        all_videos.extend(_search_with_api(q))
        time.sleep(0.8)

    # إزالة تكرار
    seen = set()
    unique_videos = [v for v in all_videos if v["id"] not in seen and not seen.add(v["id"])]
    random.shuffle(unique_videos)

    for video in unique_videos:
        if len(clips) >= count:
            break
        clip_path = os.path.join(CLIPS_DIR, f"yt_{_sanitize_id(video['id'])}.mp4")
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append({"path": clip_path, "description": video["title"], "youtube_url": video["url"]})
            continue

        tmp = _download_video(video["url"], video["id"])
        if tmp and _cut_clip(tmp, clip_path, clip_duration or 20):
            clips.append({"path": clip_path, "description": video["title"], "youtube_url": video["url"]})
            print(f"  ✅ جاهز: {video['title'][:50]}")
        if tmp and os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

    return clips

def fetch_cat_clips(count: int = 10, clip_duration: float = None) -> list:
    os.makedirs(CLIPS_DIR, exist_ok=True)
    if clip_duration is None:
        clip_duration = min(TARGET_VIDEO_DURATION / count, CLIP_MAX_DURATION)

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ استخدام {count} كليب موجود")
        return random.sample(existing, count)

    needed = count - len(existing)
    yt_clips = _fetch_from_youtube(needed, clip_duration)
    clips = existing + yt_clips

    while len(clips) < count and clips:
        clips.append(random.choice(clips))

    print(f"✅ إجمالي {len(clips)} مقطع جاهز!")
    return clips[:count]

def _get_existing_clips() -> list:
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = []
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4") and not f.startswith("_tmp"):
            full = os.path.join(CLIPS_DIR, f)
            if os.path.getsize(full) > 10_000:
                clips.append({"path": full, "description": f"cached: {f}", "youtube_url": ""})
    random.shuffle(clips)
    return clips
