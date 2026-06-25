# video_fetcher.py - جلب مقاطع حيوانات مضحكة من يوتيوب

import os
import random
import subprocess
import json
import time
import re
from config import OUTPUT_DIR

CLIPS_DIR = os.path.join(OUTPUT_DIR, "cat_clips")

CLIP_MIN_DURATION = 4.0
CLIP_MAX_DURATION = 30.0
TARGET_VIDEO_DURATION = 300

YOUTUBE_QUERIES = [
    "funny cats", "cute kittens", "hilarious cats", "cat fails",
    "funny dogs", "cute funny animals", "kittens playing", "funny pets",
    "puppy fails", "hilarious pets", "funny cat videos"
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


def _search_youtube(query: str, max_results: int = 12) -> list:
    try:
        cmd = [
            "yt-dlp", "--dump-json", "--flat-playlist", "--no-playlist",
            "--match-filter", "duration > 15 & duration < 180",
            "--quiet", "--no-warnings", "--js-runtimes", "deno",
            "--extractor-args", "youtube:player_client=web,ios,android,web_embedded",
            "--ignore-errors", f"ytsearch{max_results}:{query}"
        ]
        print(f"  🔍 بحث: {query}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)

        results = []
        for line in r.stdout.strip().split("\n"):
            if line.strip():
                try:
                    info = json.loads(line)
                    dur = info.get("duration") or 0
                    if CLIP_MIN_DURATION <= dur <= 180:
                        results.append({
                            "id": info.get("id", ""),
                            "url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id','')}",
                            "title": info.get("title", query),
                            "duration": dur,
                        })
                except:
                    continue
        print(f"     ✅ وجدنا {len(results)} فيديو")
        return results
    except Exception as e:
        print(f"  ⚠️ خطأ بحث: {e}")
        return []


def _download_video(url: str, video_id: str) -> str | None:
    safe_id = _sanitize_id(video_id)
    tmp_path = os.path.join(CLIPS_DIR, f"_tmp_{safe_id}.mp4")

    if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 10_000:
        return tmp_path

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best",
        "--merge-output-format", "mp4",
        "--no-playlist", "--quiet", "--no-warnings",
        "--js-runtimes", "deno",
        "--extractor-args", "youtube:player_client=ios,android,web",
        "--ignore-errors",
        "-o", tmp_path,
        url,
    ]
    
    print(f"  ⬇️ تحميل: {video_id}")
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=180)
        if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 3_000_000:
            print(f"  ✅ تحميل ناجح")
            return tmp_path
        else:
            print(f"  ⚠️ تحميل فشل | exit: {r.returncode}")
            return None
    except Exception as e:
        print(f"  ⚠️ خطأ تحميل: {e}")
        return None


def _fetch_from_youtube(count: int, clip_duration: float) -> list:
    print(f"  🎬 جاري البحث عن {count} فيديو...")
    clips = []
    queries = random.sample(YOUTUBE_QUERIES, min(6, len(YOUTUBE_QUERIES)))
    all_videos = []

    for q in queries:
        all_videos.extend(_search_youtube(q))
        time.sleep(1.2)

    # إزالة التكرارات
    seen = set()
    unique_videos = [v for v in all_videos if v["id"] not in seen and not seen.add(v["id"])]

    random.shuffle(unique_videos)

    for video in unique_videos[:count*2]:   # نجرب أكتر عشان نتأكد
        if len(clips) >= count:
            break

        clip_path = os.path.join(CLIPS_DIR, f"yt_{_sanitize_id(video['id'])}.mp4")
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 10_000:
            clips.append({"path": clip_path, "description": video["title"], "youtube_url": video["url"]})
            continue

        tmp = _download_video(video["url"], video["id"])
        if tmp and _cut_clip(tmp, clip_path, clip_duration or 20):
            clips.append({"path": clip_path, "description": video["title"], "youtube_url": video["url"]})
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass

    return clips


def fetch_cat_clips(count: int = 10, clip_duration: float = None) -> list:
    os.makedirs(CLIPS_DIR, exist_ok=True)
    if clip_duration is None:
        clip_duration = min(TARGET_VIDEO_DURATION / count, CLIP_MAX_DURATION)

    existing = _get_existing_clips()
    if len(existing) >= count:
        return random.sample(existing, count)

    yt_clips = _fetch_from_youtube(count - len(existing), clip_duration)
    clips = existing + yt_clips

    while len(clips) < count and clips:
        clips.append(random.choice(clips))

    print(f"✅ {len(clips)} مقطع جاهز!")
    return clips[:count]


def _get_existing_clips() -> list:
    if not os.path.exists(CLIPS_DIR):
        return []
    clips = []
    for f in os.listdir(CLIPS_DIR):
        if f.endswith(".mp4") and not f.startswith("_tmp") and os.path.getsize(os.path.join(CLIPS_DIR, f)) > 10_000:
            clips.append({"path": os.path.join(CLIPS_DIR, f), "description": f"cached: {f}", "youtube_url": ""})
    random.shuffle(clips)
    return clips


if __name__ == "__main__":
    clips = fetch_cat_clips(5)
    print(f"تم جلب {len(clips)} كليب")
