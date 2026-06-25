# video_fetcher.py - جلب فيديوهات raw قصيرة

import os
import random
import subprocess
import json
import time
import re
import requests
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

# إعدادات جديدة للـ Raw
CLIP_MIN_DURATION = 8.0
CLIP_MAX_DURATION = 60.0   # فيديوهات قصيرة raw
TARGET_VIDEO_DURATION = 300

YOUTUBE_QUERIES = [
    "funny cats", "cute kittens", "cat fails", "hilarious cats",
    "funny dogs", "cute funny animals", "kittens playing", "funny pets",
    "cat shorts", "funny cat shorts", "kitten shorts"
]

def _get_duration(path: str) -> float | None:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
                           capture_output=True, text=True, timeout=15)
        return float(json.loads(r.stdout)["format"]["duration"])
    except:
        return None

def _sanitize_id(video_id: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', video_id)

def _search_with_api(query: str, max_results: int = 10) -> list:
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
        "videoDuration": "short",   # فيديوهات قصيرة
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
    final_path = os.path.join(CLIPS_DIR, f"yt_{safe_id}.mp4")   # raw

    if os.path.exists(final_path) and os.path.getsize(final_path) > 10_000:
        return final_path

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=ios,android,web",
        "--ignore-errors",
        "-o", final_path,
        url
    ]
    
    print(f"  ⬇️ تحميل raw: {video_id}")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=240)
        if r.returncode == 0 and os.path.exists(final_path) and os.path.getsize(final_path) > 3_000_000:
            print(f"  ✅ تحميل raw ناجح")
            return final_path
        else:
            print(f"  ⚠️ فشل التحميل: {video_id}")
            return None
    except Exception as e:
        print(f"  ⚠️ خطأ تحميل: {e}")
        return None

def _fetch_from_youtube(count: int) -> list:
    print(f"  🎬 جاري جلب {count} فيديو raw...")
    clips = []
    queries = random.sample(YOUTUBE_QUERIES, min(6, len(YOUTUBE_QUERIES)))
    all_videos = []

    for q in queries:
        all_videos.extend(_search_with_api(q))
        time.sleep(1.0)

    seen = set()
    unique_videos = [v for v in all_videos if v["id"] not in seen and not seen.add(v["id"])]
    random.shuffle(unique_videos)

    for video in unique_videos:
        if len(clips) >= count:
            break

        clip_path = _download_video(video["url"], video["id"])
        if clip_path:
            clips.append({
                "path": clip_path,
                "description": video["title"],
                "youtube_url": video["url"]
            })
            print(f"  ✅ raw جاهز: {video['title'][:60]}")

    print(f"  📊 نجح {len(clips)} raw فيديو")
    return clips

def fetch_cat_clips(count: int = 10) -> list:
    os.makedirs(CLIPS_DIR, exist_ok=True)

    existing = _get_existing_clips()
    if len(existing) >= count:
        print(f"✅ استخدام {count} كليب raw موجود")
        return random.sample(existing, count)

    needed = count - len(existing)
    yt_clips = _fetch_from_youtube(needed)
    clips = existing + yt_clips

    while len(clips) < count and clips:
        clips.append(random.choice(clips))

    print(f"✅ إجمالي {len(clips)} فيديو raw جاهز!")
    return clips[:count]

def _get_existing_clips() -> list:
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = []
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4") and not f.startswith("_tmp"):
            full = os.path.join(CLIPS_DIR, f)
            if os.path.getsize(full) > 10_000:
                clips.append({"path": full, "description": f"cached raw: {f}", "youtube_url": ""})
    random.shuffle(clips)
    return clips
