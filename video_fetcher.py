import os
import subprocess
import time
import random
from datetime import datetime

CLIPS_DIR = "clips"

def _sanitize_id(video_id: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in video_id)[:20]

def _search_with_yt_dlp(query: str, max_results: int = 8):
    print(f"   🔍 بحث: {query}")
    try:
        cmd = [
            "yt-dlp", f"ytsearch{max_results}:{query}",
            "--flat-playlist", "--print", "%(id)s %(title)s", "--quiet",
            "--extractor-args", "youtube:player_client=ios,web"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        videos = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(' ', 1)
                if len(parts) >= 2:
                    videos.append({
                        "id": parts[0].strip(),
                        "url": f"https://www.youtube.com/watch?v={parts[0].strip()}",
                        "title": parts[1].strip()
                    })
        print(f"   ✅ وجد {len(videos)} فيديو")
        return videos
    except Exception as e:
        print(f"   ❌ خطأ في البحث: {e}")
        return []

def _download_video(url: str, video_id: str) -> str | None:
    safe_id = _sanitize_id(video_id)
    final_path = os.path.join(CLIPS_DIR, f"yt_{safe_id}.mp4")

    if os.path.exists(final_path) and os.path.getsize(final_path) > 500_000:
        print(f"   ✅ موجود مسبقاً: {safe_id}")
        return final_path

    cmd = [
        "yt-dlp",
        "--cookies-from-browser", "chrome",
        "-f", "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--retries", "5",
        "--fragment-retries", "5",
        "--extractor-args", "youtube:player_client=ios,web,android",
        "--ignore-errors",
        "-o", final_path,
        url
    ]
    
    print(f"   ⬇️ تحميل: {video_id}")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
        
        if r.returncode == 0 and size > 800_000:
            print(f"   ✅ نجح ({size // (1024*1024)} MB)")
            return final_path
        else:
            print(f"   ⚠️ فشل أو حجم صغير ({size} bytes) | code={r.returncode}")
            if os.path.exists(final_path):
                os.remove(final_path)
            return None
    except Exception as e:
        print(f"   ⚠️ خطأ تحميل: {e}")
        return None

def fetch_cat_clips(count: int = 10):
    os.makedirs(CLIPS_DIR, exist_ok=True)
    
    QUERIES = [
        "funny cats", "cute kittens", "cat fails", "hilarious cats",
        "kittens playing", "funny cat videos", "cat comedy",
        "cute cat shorts", "funny kitten fails", "cats being silly",
        "adorable kittens", "cat zoomies", "silly cats"
    ]
    
    all_videos = []
    downloaded = []
    
    random.shuffle(QUERIES)
    
    for q in QUERIES[:6]:  # 6 queries كفاية
        videos = _search_with_yt_dlp(q, max_results=6)
        all_videos.extend(videos)
        
        for video in videos[:count - len(downloaded)]:
            path = _download_video(video["url"], video["id"])
            if path:
                downloaded.append({
                    "path": path,
                    "title": video["title"],
                    "id": video["id"]
                })
            if len(downloaded) >= count:
                break
        if len(downloaded) >= count:
            break
        time.sleep(3)
    
    print(f"📥 تم تحميل {len(downloaded)} كليب قطط")
    return downloaded

if __name__ == "__main__":
    fetch_cat_clips(12)
