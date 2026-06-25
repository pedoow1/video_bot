import os
import subprocess
import time
import random

CLIPS_DIR = "clips"

def _sanitize_id(video_id: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in video_id)[:20]

def _search_with_yt_dlp(query: str, max_results: int = 10):
    print(f"   🔍 بحث: {query}")
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{max_results}:{query}",
            "--flat-playlist",
            "--print", "%(id)s %(title)s %(duration)s",
            "--match-filter", "duration < 65",   # تحت 65 ثانية (هامش صغير)
            "--quiet",
            "--no-warnings"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        videos = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(' ', 2)
                if len(parts) >= 2:
                    videos.append({
                        "id": parts[0].strip(),
                        "url": f"https://www.youtube.com/watch?v={parts[0].strip()}",
                        "title": parts[1].strip()
                    })
        print(f"   ✅ وجد {len(videos)} فيديو قصير")
        return videos
    except Exception as e:
        print(f"   ❌ خطأ بحث: {e}")
        return []

def _download_video(url: str, video_id: str) -> str | None:
    safe_id = _sanitize_id(video_id)
    final_path = os.path.join(CLIPS_DIR, f"yt_{safe_id}.mp4")

    if os.path.exists(final_path) and os.path.getsize(final_path) > 300_000:
        print(f"   ✅ موجود: {safe_id}")
        return final_path

    print(f"   ⬇️ تحميل: {video_id} ...")

    # 🔥 أفضل command حالياً للـ Shorts (بناءً على أحدث الحلول)
    cmd = [
        "yt-dlp",
        "-f", "best[ext=mp4]/best",           # مرن جداً
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--format-sort", "res:720",           # أولوية 720p
        "--retries", "15",
        "--fragment-retries", "15",
        "--extractor-args", "youtube:player_client=ios,web,android,web_safari",
        "--user-agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15",
        "--ignore-errors",
        "--no-warnings",
        "--concurrent-fragments", "6",
        "-o", final_path,
        url
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        size = os.path.getsize(final_path) if os.path.exists(final_path) else 0

        if r.returncode == 0 and size > 500_000:
            print(f"   ✅ نجح! ({size // (1024*1024)} MB)")
            return final_path
        else:
            print(f"   ❌ فشل (size={size} bytes | code={r.returncode})")
            if r.stderr:
                print(f"   stderr: {r.stderr[-900:]}")
            if os.path.exists(final_path):
                os.remove(final_path)
            return None
    except Exception as e:
        print(f"   ⚠️ Exception: {e}")
        return None

def fetch_cat_clips(count: int = 10):
    os.makedirs(CLIPS_DIR, exist_ok=True)
    
    QUERIES = [
        "funny cats", "cute kittens", "cat fails", "hilarious cats",
        "kittens playing", "funny cat videos", "cat comedy", "silly cats"
    ]
    
    downloaded = []
    random.shuffle(QUERIES)
    
    print(f"\n🎥 جلب {count} كليبات قطط قصيرة (< 65 ثانية)...\n")
    
    for q in QUERIES[:6]:
        videos = _search_with_yt_dlp(q, max_results=12)
        for video in videos:
            if len(downloaded) >= count:
                break
            path = _download_video(video["url"], video["id"])
            if path:
                downloaded.append({"path": path, "title": video["title"], "id": video["id"]})
        if len(downloaded) >= count:
            break
        time.sleep(5)
    
    print(f"\n📥 تم تحميل {len(downloaded)} كليب قطط")
    return downloaded

if __name__ == "__main__":
    fetch_cat_clips(10)
