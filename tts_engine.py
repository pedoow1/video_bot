# tts_engine.py - Edge-TTS للسرد + Freesound للمؤثرات الصوتية

import os
import asyncio
import subprocess
import requests
import random
import time
from config import OUTPUT_DIR, FREESOUND_API_KEY

AUDIO_DIR = os.path.join(OUTPUT_DIR, "audio")

# ==============================
#  Edge-TTS
# ==============================

EDGE_TTS_VOICES = [
    "en-US-GuyNeural",
    "en-US-ChristopherNeural",
    "en-GB-RyanNeural",
    "en-US-EricNeural",
]
EDGE_TTS_VOICE = EDGE_TTS_VOICES[0]


def _install_edge_tts():
    try:
        import edge_tts
    except ImportError:
        print("📦 جاري تثبيت edge-tts...")
        subprocess.run(["pip", "install", "edge-tts", "-q"], check=True)
        print("✅ edge-tts اتثبت")


async def _synthesize_with_timings(text: str, out_path: str, voice: str = EDGE_TTS_VOICE):
    """
    يولّد الصوت ويجمع word timings في نفس الـ stream.
    يرجع list من (word, start_sec, end_sec).
    لو WordBoundary مرجعتش، يولد timings تقريبية من مدة الصوت.
    """
    import edge_tts

    word_timings = []
    audio_chunks = []

    communicate = edge_tts.Communicate(text, voice)
    async for event in communicate.stream():
        if event["type"] == "audio":
            audio_chunks.append(event["data"])
        elif event["type"] == "WordBoundary":
            word  = event["text"]
            start = event["offset"]   / 10_000_000
            dur   = event["duration"] / 10_000_000
            word_timings.append((word, start, start + dur))

    # احفظ الصوت
    with open(out_path, "wb") as f:
        for chunk in audio_chunks:
            f.write(chunk)

    # لو WordBoundary مرجعتش — نولد timings تقريبية
    if not word_timings and os.path.exists(out_path):
        print("  ⚠️ WordBoundary مرجعتش — بيولد timings تقريبية...")
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", out_path],
            capture_output=True, text=True
        )
        try:
            total_dur = float(result.stdout.strip())
        except Exception:
            total_dur = len(text.split()) * 0.35

        words = text.split()
        if words:
            dur_per_word = total_dur / len(words)
            for i, word in enumerate(words):
                start = i * dur_per_word
                word_timings.append((word, start, start + dur_per_word))
            print(f"  ✅ timings تقريبية: {len(word_timings)} كلمة")

    return word_timings


def synthesize_with_timings(text: str, out_path: str, voice: str = EDGE_TTS_VOICE) -> list:
    """Sync wrapper — يولّد الصوت ويرجع word timings."""
    _install_edge_tts()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        timings = loop.run_until_complete(_synthesize_with_timings(text, out_path, voice))
        loop.close()
        return timings
    except Exception as e:
        print(f"  ⚠️ synthesize_with_timings فشل: {e}")
        _synthesize_fallback(text, out_path, voice)
        return []


async def _synthesize_fallback_async(text: str, out_path: str, voice: str):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def _synthesize_fallback(text: str, out_path: str, voice: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_synthesize_fallback_async(text, out_path, voice))
    loop.close()


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except (ValueError, TypeError):
        return 60.0


def _ffmpeg_convert(src_path: str, dst_path: str):
    subprocess.run(
        ["ffmpeg", "-y", "-i", src_path, dst_path],
        capture_output=True, check=True
    )


def _stitch_audio(chunk_paths: list, output_path: str):
    list_file = output_path + ".concat.txt"
    with open(list_file, "w") as f:
        for p in chunk_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy" if output_path.endswith(".mp3") else "pcm_s16le",
         output_path],
        capture_output=True, check=True
    )
    os.remove(list_file)


def text_to_speech_paragraphs(paragraphs: list, base_filename: str = "audio") -> dict:
    """
    يحوّل كل فقرة لصوت + يجمع word timings بالتوقيت الـ absolute.
    يرجع dict: audio_path, durations, start_times, total_duration, word_timings
    """
    _install_edge_tts()
    os.makedirs(AUDIO_DIR, exist_ok=True)

    paragraph_paths  = []
    durations        = []
    all_word_timings = []

    print(f"🎙️ توليد صوت + word timings لكل فقرة ({len(paragraphs)} فقرة)...")

    cumulative_offset = 0.0

    for i, para in enumerate(paragraphs):
        p_path = os.path.join(AUDIO_DIR, f"_para_{i}.mp3")
        print(f"  🔊 فقرة {i+1}/{len(paragraphs)}...")

        timings = synthesize_with_timings(para, p_path, EDGE_TTS_VOICE)

        d = get_audio_duration(p_path)
        paragraph_paths.append(p_path)
        durations.append(d)

        if not timings:
            print(f"     ⚠️ فقرة {i+1}: مفيش word timings — subtitles مش هتظهر لهذه الفقرة")
        else:
            print(f"     ⏱️ {d:.1f}s — {len(timings)} كلمة ✅")

        # تحويل timing من relative → absolute
        for word, rel_start, rel_end in timings:
            all_word_timings.append((word,
                                     rel_start + cumulative_offset,
                                     rel_end   + cumulative_offset))

        cumulative_offset += d

    # دمج ملفات الصوت
    if base_filename.lower().endswith((".wav", ".mp3")):
        final_filename = base_filename
    else:
        final_filename = f"{base_filename}.wav"
    output_path = os.path.join(AUDIO_DIR, final_filename)

    if len(paragraph_paths) == 1:
        _ffmpeg_convert(paragraph_paths[0], output_path)
    else:
        _stitch_audio(paragraph_paths, output_path)

    for p in paragraph_paths:
        try:
            os.remove(p)
        except OSError:
            pass

    start_times = []
    cum = 0.0
    for d in durations:
        start_times.append(cum)
        cum += d

    total = cum
    print(f"✅ الصوت جاهز: {output_path} ({total:.0f}s) — {len(all_word_timings)} كلمة")

    return {
        "audio_path":     output_path,
        "durations":      durations,
        "start_times":    start_times,
        "total_duration": total,
        "word_timings":   all_word_timings,
    }


def text_to_speech(text: str, filename: str = "audio.wav") -> str:
    os.makedirs(AUDIO_DIR, exist_ok=True)
    output_path = os.path.join(AUDIO_DIR, filename)
    tmp_path = output_path + "_tmp.mp3"
    print(f"🎙️ Edge-TTS ({EDGE_TTS_VOICE})...")
    _synthesize_fallback(text, tmp_path, EDGE_TTS_VOICE)
    if not output_path.endswith(".mp3"):
        _ffmpeg_convert(tmp_path, output_path)
        os.remove(tmp_path)
    else:
        os.rename(tmp_path, output_path)
    print(f"✅ الصوت جاهز: {output_path}")
    return output_path


# ==============================
#  Freesound - مع rate limiting
# ==============================

FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
_last_freesound_call = 0.0
FREESOUND_MIN_INTERVAL = 2.5

MOOD_SFX_KEYWORDS = {
    "mysterious": ["mystery ambience", "suspense drone", "eerie wind"],
    "scary":      ["horror ambience", "scary sound", "dark drone"],
    "romantic":   ["romantic ambience", "soft wind", "gentle water"],
    "happy":      ["cheerful birds", "uplifting ambience", "nature sounds"],
    "sad":        ["sad piano ambience", "rain gentle", "melancholy"],
    "adventure":  ["adventure wind", "epic ambience", "dramatic atmosphere"],
    "dark":       ["dark ambience", "ominous drone", "dark atmosphere"],
}


def search_freesound(query: str, duration_max: float = 10.0) -> dict:
    global _last_freesound_call
    elapsed = time.time() - _last_freesound_call
    if elapsed < FREESOUND_MIN_INTERVAL:
        wait = FREESOUND_MIN_INTERVAL - elapsed
        print(f"  ⏳ Freesound — انتظار {wait:.1f}s")
        time.sleep(wait)

    params = {
        "query":     query,
        "token":     FREESOUND_API_KEY,
        "fields":    "id,name,duration,previews,license",
        "filter":    f"duration:[0.5 TO {duration_max}]",
        "page_size": 10,
        "sort":      "rating_desc",
    }
    try:
        r = requests.get(FREESOUND_SEARCH_URL, params=params, timeout=15)
        _last_freesound_call = time.time()
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            return random.choice(results[:min(5, len(results))])
    except Exception as e:
        _last_freesound_call = time.time()
        print(f"  ⚠️ Freesound: {e}")
    return None


def download_freesound(sound: dict, out_path: str) -> bool:
    try:
        previews = sound.get("previews", {})
        url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
        if not url:
            return False
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"  ⚠️ Freesound download: {e}")
        return False


def generate_sound_effect(prompt: str, out_path: str, duration_seconds: float = None) -> str:
    print(f"  🔍 بيدور على مؤثر: {prompt}")
    max_dur = duration_seconds or 10.0
    sound = search_freesound(prompt, max_dur)
    if not sound:
        sound = search_freesound(" ".join(prompt.split()[:3]), max_dur)
    if not sound:
        sound = search_freesound("ambient atmosphere", max_dur)
    if not sound:
        raise RuntimeError(f"Freesound: مافيش نتائج لـ '{prompt}'")
    print(f"  ✅ لقى: {sound.get('name','?')}")
    if not download_freesound(sound, out_path):
        raise RuntimeError("Freesound: فشل التحميل")
    return out_path


def fetch_mood_sfx(mood: str, out_path: str, duration_max: float = 10.0) -> str:
    keywords = MOOD_SFX_KEYWORDS.get(mood, ["ambient atmosphere"])
    query    = random.choice(keywords)
    sound    = search_freesound(query, duration_max)
    if not sound:
        sound = search_freesound("ambient atmosphere", duration_max)
    if not sound:
        return None
    download_freesound(sound, out_path)
    return out_path


if __name__ == "__main__":
    import sys
    if "--sfx" in sys.argv:
        print("🔊 اختبار Freesound...")
        generate_sound_effect("mysterious wind desert", "test_sfx.mp3", 5.0)
    else:
        print("🎙️ اختبار Edge-TTS + word timings...")
        result = text_to_speech_paragraphs(
            ["Once upon a time, a clockmaker found a strange mechanism buried in the desert."],
            "test_audio"
        )
        print(f"✅ الصوت: {result['audio_path']}")
        print("أول 5 كلمات:")
        for w, s, e in result["word_timings"][:5]:
            print(f"  '{w}' → {s:.2f}s – {e:.2f}s")
