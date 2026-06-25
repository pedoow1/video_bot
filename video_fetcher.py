import os
import subprocess
import time
import random
from datetime import datetime

def _download_video(url: str, output_path: str) -> bool:
    """تحميل فيديو باستخدام yt-dlp مع cookies"""
    try:
        cmd = [
            "yt-dlp",
            "--cookies-from-browser", "chrome",   # أو يستخدم الـ secret تلقائي
            "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best",
            "--merge-output-format", "mp4",
            "--retries", "15",
            "--fragment-retries", "15",
            "--abort-on-unavailable-fragment",
            "--extractor-args", "youtube:player_client=ios,web,android",
            "--no-abort-on-error",
            "--ignore-errors",
            "--sleep-interval", "3",
            "-o", output_path,
            url
        ]
        
        print(f"   ⬇️ جاري تحميل: {url}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"   ✅ تم التحميل بنجاح: {output_path}")
            return True
        else:
            print(f"   ❌ فشل التحميل: {result.stderr[-300:]}")
            return False
    except Exception as e:
        print(f"   ❌ خطأ في التحميل: {e}")
        return False


def _search_with_yt_dlp(query: str, max_results: int = 10):
    """بحث باستخدام yt-dlp فقط (بدون API Key)"""
    print(f"   🔍 جاري البحث عن: {query}")
    try:
        cmd = [
            "yt-dlp",
            f"ytsearch{max_results}:{query}",
            "--flat-playlist",
            "--print", "%(id)s %(title)s",
            "--quiet"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        
        videos = []
        for line in result.stdout.strip().split('\n'):
            if line.strip():
                parts = line.split(' ', 1)
                if len(parts) >= 2:
                    vid_id = parts[0].strip()
                    title = parts[1].strip()
                    videos.append({
                        "id": vid_id,
                        "url": f"https://www.youtube.com/watch?v={vid_id}",
                        "title": title
                    })
        print(f"   ✅ yt-dlp وجد {len(videos)} فيديو")
        return videos[:max_results]
    except Exception as e:
        print(f"   ⚠️ خطأ في البحث: {e}")
        return []


def fetch_cat_clips(count: int = 5):
    """جلب كليبات قطط"""
    queries = [
        "funny cats", "cute kittens", "cat compilation", 
        "cats being silly", "kittens playing", "funny cat videos"
    ]
    
    all_videos = []
    for query in queries:
        if len(all_videos) >= count * 2:
            break
        videos = _search_with_yt_dlp(query, max_results=8)
        all_videos.extend(videos)
        time.sleep(2)
    
    # إزالة التكرارات
    unique_videos = {v["id"]: v for v in all_videos}.values()
    return list(unique_videos)[:count]


def run_cat_pipeline():
    """الـ Pipeline الرئيسي للقطط"""
    print(f"\n🐱 {datetime.now().strftime('%d-%m-%Y')} - بدء إنتاج فيديو قطط")
    
    videos = fetch_cat_clips(count=8)
    
    if not videos:
        print("❌ لم يتم العثور على أي فيديوهات")
        return False
    
    print(f"📥 تم جلب {len(videos)} فيديو raw")
    
    # هنا يمكن إضافة دمج الفيديوهات بـ ffmpeg لاحقًا
    print("✅ Cat Pipeline نجح (جاهز للمعالجة)")
    return True


if __name__ == "__main__":
    run_cat_pipeline()
