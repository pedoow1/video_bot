import os
import subprocess
import time
import random

CLIPS_DIR = "clips"

def _sanitize_id(video_id: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in video_id)[:20]

def _search_with_yt_dlp(query: str, max_results: int = 8):
    print(f"   🔍 بحث: {query}")
    try:
        cmd = [
            "yt-dlp", f"ytsearch{max_results}:{query}",
            "--flat-playlist", "--print", "%(id)s %(title)s",
            "--quiet", "--no-warnings"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
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
        print(f"   ❌ خطأ بحث: {e}")
        return []

def _download_video(url: str, video_id: str) -> str | None:
    safe_id = _sanitize_id(video_id)
    final_path = os.path.join(CLIPS_DIR, f"yt_{safe_id}.mp4")

    if os.path.exists(final_path) and os.path.getsize(final_path) > 300_000:
        print(f"   ✅ موجود: {safe_id}")
        return final_path

    print(f"   ⬇️ تحميل: {video_id} ...")

    # أبسط وأقوى command لـ GitHub Actions
    cmd = [
        "yt-dlp",
        "-f", "best",                    # أبسط format (combined)
        "--merge-output-format", "mp4",
        "--no-playlist",
        "--retries", "12",
        "--fragment-retries", "12",
        "--extractor-args", "youtube:player_client=ios,web,android",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "--ignore-errors",
        "--no-warnings",
        "-o", final_path,
        url
    ]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        size = os.path.getsize(final_path) if os.path.exists(final_path) else 0

        if r.returncode == 0 and size > 600_000:
            print(f"   ✅ نجح! ({size // (1024*1024)} MB)")
            return final_path
        else:
            print(f"   ❌ فشل (size={size} bytes | code={r.returncode})")
            if r.stderr:
                print(f"   stderr: {r.stderr[-600:]}")
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
    
    print(f"\n🎥 جلب {count} كليبات قطط...\n")
    
    for q in QUERIES[:5]:
        videos = _search_with_yt_dlp(q, max_results=8)
        for video in videos:
            if len(downloaded) >= count:
                break
            path = _download_video(video["url"], video["id"])
            if path:
                downloaded.append({"path": path, "title": video["title"], "id": video["id"]})
        if len(downloaded) >= count:
            break
        time.sleep(6)
    
    print(f"\n📥 تم تحميل {len(downloaded)} كليب قطط")
    return downloaded

if __name__ == "__main__":
    fetch_cat_clips(10)
