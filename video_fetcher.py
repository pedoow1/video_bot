import os
import subprocess
import time
import random
from datetime import datetime

def _search_with_yt_dlp(query: str, max_results: int = 8):
    print(f"   🔍 بحث: {query}")
    try:
        cmd = [
            "yt-dlp", f"ytsearch{max_results}:{query}",
            "--flat-playlist", "--print", "%(id)s %(title)s", "--quiet"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
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
    except:
        return []


def download_clips(videos, download_dir="clips"):
    os.makedirs(download_dir, exist_ok=True)
    downloaded = []
    for i, video in enumerate(videos[:10]):   # حمل أول 10
        path = f"{download_dir}/clip_{i:03d}.mp4"
        try:
            cmd = [
                "yt-dlp",
                "--cookies-from-browser", "chrome",
                "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best",
                "--merge-output-format", "mp4",
                "--retries", "10",
                "-o", path,
                video["url"]
            ]
            print(f"   ⬇️ تحميل {i+1}/{len(videos)}")
            subprocess.run(cmd, timeout=120, check=True)
            if os.path.exists(path):
                downloaded.append(path)
        except:
            continue
        time.sleep(2)
    return downloaded


def create_final_video(clips, output="final_video.mp4"):
    if len(clips) < 3:
        print("❌ عدد الكليبات قليل")
        return False

    # إنشاء ملف list لـ ffmpeg
    with open("clips_list.txt", "w") as f:
        for clip in clips:
            f.write(f"file '{clip}'\n")

    print("✂️ جاري دمج الفيديوهات...")
    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", "clips_list.txt",
        "-c", "copy", "-y", output
    ]
    try:
        subprocess.run(cmd, check=True, timeout=60)
        print(f"✅ تم إنشاء الفيديو النهائي: {output}")
        return True
    except Exception as e:
        print(f"❌ خطأ في الدمج: {e}")
        return False


def run_cat_pipeline():
    print(f"\n🐱 {datetime.now().strftime('%d-%m-%Y %H:%M')} - بدء إنتاج فيديو قطط")
    
    queries = ["funny cats", "cute kittens", "cat compilation", "kittens playing"]
    all_videos = []
    
    for q in queries:
        videos = _search_with_yt_dlp(q)
        all_videos.extend(videos)
        if len(all_videos) >= 12:
            break
        time.sleep(3)

    clips = download_clips(all_videos, "clips")
    print(f"📥 تم تحميل {len(clips)} كليب")

    if create_final_video(clips):
        print("🎉 الفيديو النهائي جاهز!")
        return True
    return False


if __name__ == "__main__":
    run_cat_pipeline()
