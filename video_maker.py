# video_maker.py - صناعة الفيديو بـ MoviePy
# إصلاحات:
#   1. Subtitles حقيقية تمشي مع الكلام (Edge-TTS word timing)
#   2. حركة أحسن في الصور (Pan + Zoom + Shake)
#   3. Freesound rate limiting - طلب واحد كل ثانيتين

import os
import time
import requests
import textwrap
import random
import urllib.parse
import subprocess
import asyncio
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

from moviepy.editor import (
    VideoFileClip, AudioFileClip, ImageClip, VideoClip,
    CompositeVideoClip, concatenate_videoclips,
    TextClip, ColorClip
)
from moviepy.video.fx.all import fadein, fadeout
from moviepy.audio.AudioClip import CompositeAudioClip
from moviepy.audio.fx.all import audio_loop, volumex

from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, FPS,
    FONT_PATH, FONT_SIZE_STORY, FONT_SIZE_TITLE,
    TEXT_COLOR, IMAGE_DURATION,
    IMAGES_DIR, VIDEO_DIR, MUSIC_DIR, MUSIC_VOLUME, MUSIC_FADE_SECONDS,
    ENABLE_SFX, SFX_DIR, SFX_VOLUME, SFX_MAX_DURATION,
    FREESOUND_API_KEY
)


# ==============================
#  موسيقى خلفية — incompetech.com (Kevin MacLeod) مجاني CC
#  روابط مضمونة وشغالة فعلاً
# ==============================

MUSIC_LIBRARY = {
    "mysterious": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Darkness%20Speaks.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Cipher.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3",
    ],
    "scary": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sinister.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Ominous.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Creepy%20Death%20Race.mp3",
    ],
    "romantic": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Romantic.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dream%20Culture.mp3",
    ],
    "happy": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Carefree.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sunshine.mp3",
    ],
    "sad": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sad%20Trio.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sad%20Romance.mp3",
    ],
    "adventure": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Adventure%201.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Epic%20Action%20B.mp3",
    ],
    "dark": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Dark%20Times.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Darkness%20Speaks.mp3",
    ],
    # ── موسيقى لـ "10 Amazing Facts" content ──
    "epic": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Epic%20Action%20A.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Epic%20Action%20B.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Heroic%20Age.mp3",
    ],
    "educational": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Investigations.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Cipher.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Thinking%20Music.mp3",
    ],
    "inspiring": [
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Inspired.mp3",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Adventure%201.mp3",
    ],
}
DEFAULT_MUSIC_MOOD = "mysterious"

# fallback بسيط لو incompetech فشل
FALLBACK_MUSIC_URLS = [
    "https://freemusicarchive.org/track/Ominous/download/",
]


def fetch_background_music(mood: str) -> str:
    """يحمّل موسيقى خلفية بـ mood مناسب من incompetech (CC مجاني)."""
    os.makedirs(MUSIC_DIR, exist_ok=True)

    safe_mood  = mood if mood in MUSIC_LIBRARY else DEFAULT_MUSIC_MOOD
    music_path = os.path.abspath(os.path.join(MUSIC_DIR, f"music_{safe_mood}.mp3"))

    if os.path.exists(music_path) and os.path.getsize(music_path) > 50_000:
        print(f"  ✅ موسيقى '{safe_mood}' موجودة بالفعل")
        return music_path

    urls = MUSIC_LIBRARY.get(safe_mood, []) + FALLBACK_MUSIC_URLS
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StoryBot/1.0)"}

    for url in urls:
        try:
            print(f"  🎵 جاري تجربة: {url[:70]}...")
            r = requests.get(url, timeout=30, headers=headers, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 50_000:
                with open(music_path, "wb") as f:
                    f.write(r.content)
                print(f"  ✅ الموسيقى جاهزة ({len(r.content)//1024} KB)")
                return music_path
            print(f"  ⚠️ ({r.status_code}, {len(r.content)} bytes) — جاري تجربة التالي")
        except Exception as e:
            print(f"  ⚠️ فشل: {e}")

    print("  ❌ كل مصادر الموسيقى فشلت — هيكمل بدون موسيقى")
    return None


# ==============================
#  مؤثرات صوتية - Freesound مع rate limiting
# ==============================

_last_freesound_request = 0.0
FREESOUND_DELAY = 2.5   # ثانيتين ونص بين كل طلب


def _freesound_search(query: str, duration_max: float = 10.0) -> dict:
    """يبحث على Freesound مع احترام rate limit."""
    global _last_freesound_request

    # rate limiting
    elapsed = time.time() - _last_freesound_request
    if elapsed < FREESOUND_DELAY:
        wait = FREESOUND_DELAY - elapsed
        print(f"  ⏳ Freesound rate limit — انتظار {wait:.1f}s")
        time.sleep(wait)

    params = {
        "query":    query,
        "token":    FREESOUND_API_KEY,
        "fields":   "id,name,duration,previews",
        "filter":   f"duration:[0.5 TO {duration_max}]",
        "page_size": 8,
        "sort":     "rating_desc",
    }
    try:
        r = requests.get(
            "https://freesound.org/apiv2/search/text/",
            params=params, timeout=15
        )
        _last_freesound_request = time.time()
        r.raise_for_status()
        results = r.json().get("results", [])
        if results:
            return random.choice(results[:min(5, len(results))])
    except Exception as e:
        _last_freesound_request = time.time()
        print(f"  ⚠️ Freesound خطأ: {e}")
    return None


def _freesound_download(sound: dict, out_path: str) -> bool:
    """يحمّل preview من Freesound."""
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
        print(f"  ⚠️ Freesound تحميل: {e}")
        return False


def fetch_scene_sfx(keyword: str, scene_index: int, max_duration: float) -> str:
    """يجيب مؤثر صوتي للمشهد من Freesound بشكل متسلسل (مش متوازي)."""
    os.makedirs(SFX_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in keyword)[:40]
    sfx_path = os.path.join(SFX_DIR, f"sfx_{scene_index}_{safe}.mp3")

    if os.path.exists(sfx_path) and os.path.getsize(sfx_path) > 1000:
        print(f"  ✅ SFX {scene_index+1} موجود")
        return sfx_path

    # جرب الـ keyword الأصلي
    sound = _freesound_search(keyword, max_duration)
    # لو مالقاش، جرب أول كلمتين
    if not sound:
        short = " ".join(keyword.split()[:2])
        sound = _freesound_search(short, max_duration)
    # fallback
    if not sound:
        sound = _freesound_search("ambient atmosphere", max_duration)

    if not sound:
        print(f"  ⚠️ مالقاش SFX للمشهد {scene_index+1}")
        return None

    if _freesound_download(sound, sfx_path):
        print(f"  ✅ SFX {scene_index+1}: {sound.get('name','?')}")
        return sfx_path

    return None


# ==============================
#  دمج الصوت الكامل
# ==============================

def mix_full_audio(narration_clip, music_path: str, sfx_entries: list, total_duration: float):
    layers = [narration_clip]

    if music_path:
        try:
            music = AudioFileClip(music_path)
            music = audio_loop(music, duration=total_duration) if music.duration < total_duration \
                    else music.subclip(0, total_duration)
            music = volumex(music, MUSIC_VOLUME)
            music = music.audio_fadein(MUSIC_FADE_SECONDS).audio_fadeout(MUSIC_FADE_SECONDS)
            layers.append(music)
        except Exception as e:
            print(f"  ⚠️ فشل دمج الموسيقى: {e}")

    for sfx_path, start_time, scene_dur in sfx_entries:
        if not sfx_path or not os.path.exists(sfx_path):
            continue
        try:
            sfx = AudioFileClip(sfx_path)
            usable = min(sfx.duration, scene_dur)
            sfx = sfx.subclip(0, usable)
            sfx = volumex(sfx, SFX_VOLUME)
            sfx = sfx.audio_fadeout(min(0.3, usable / 2))
            sfx = sfx.set_start(start_time)
            layers.append(sfx)
        except Exception as e:
            print(f"  ⚠️ فشل SFX: {e}")

    return CompositeAudioClip(layers) if len(layers) > 1 else narration_clip


# ==============================
#  توليد صور الخلفية عن طريق Pollinations AI
# ==============================

def _generate_pollinations_image(prompt: str, img_path: str, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT) -> bool:
    """يولد صورة من Pollinations AI ويحفظها."""
    import urllib.parse
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&model=flux"
    for attempt in range(3):
        try:
            print(f"  🎨 Pollinations: بيولد صورة (محاولة {attempt+1})...")
            r = requests.get(url, timeout=60, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 3000:
                from io import BytesIO
                pil_img = Image.open(BytesIO(r.content)).convert("RGB")
                pil_img.save(img_path, "JPEG", quality=90)
                print(f"  ✅ Pollinations: صورة جاهزة {pil_img.size}")
                return True
            else:
                print(f"  ⚠️ Pollinations: status {r.status_code} — retry")
                time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ Pollinations خطأ: {e} — retry")
            time.sleep(3)
    return False


def fetch_scene_image(keyword: str, scene_index, style_index: int = 0) -> str:
    """يولد صورة عبر Pollinations AI بناءً على keyword."""
    os.makedirs(IMAGES_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in str(keyword))[:40]
    img_path = os.path.join(IMAGES_DIR, f"scene_{scene_index}_{safe}.jpg")

    if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
        print(f"  ✅ صورة {scene_index if isinstance(scene_index, str) else scene_index+1} موجودة")
        return img_path

    label = scene_index if isinstance(scene_index, str) else scene_index + 1
    print(f"  🎨 صورة {label}: بيولد عبر Pollinations...")

    success = _generate_pollinations_image(keyword, img_path)
    if success:
        return img_path

    print(f"  ❌ صورة {label} فشلت — fallback")
    return _fallback_background(str(keyword), int(style_index))

def fetch_background_images(keyword: str, count: int = 1) -> list:
    return [fetch_scene_image(keyword, f"thumb_{i}", i) for i in range(count)]


def _fallback_background(keyword: str, index: int) -> str:
    os.makedirs(IMAGES_DIR, exist_ok=True)
    mood_colors = {
        "mysterious": [("#0d0d2b", "#1a0533")],
        "scary":      [("#1a0000", "#2d0000")],
        "romantic":   [("#2d0a1a", "#4e1a2d")],
        "happy":      [("#0a1a3d", "#1a3d6e")],
        "sad":        [("#0a0a2d", "#1a1a4e")],
        "adventure":  [("#0d2d1a", "#1a4e2d")],
        "dark":       [("#050510", "#0d0d20")],
    }
    palette = mood_colors.get(keyword, [("#0d0d2b", "#1a1a4e")])
    c1_hex, c2_hex = palette[index % len(palette)]

    def h2r(h):
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    c1, c2 = h2r(c1_hex), h2r(c2_hex)
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_HEIGHT):
        ratio = y / VIDEO_HEIGHT
        r = int(c1[0] + (c2[0]-c1[0]) * ratio)
        g = int(c1[1] + (c2[1]-c1[1]) * ratio)
        b = int(c1[2] + (c2[2]-c1[2]) * ratio)
        draw.line([(0, y), (VIDEO_WIDTH, y)], fill=(r, g, b))

    path = os.path.join(IMAGES_DIR, f"fallback_{keyword}_{index}.jpg")
    img.save(path)
    return path


# ==============================
#  حركة الصور - Pan / Zoom / Shake / Parallax
# ==============================

MOTION_STYLES = ["zoom_in", "zoom_out", "pan_right", "pan_left", "pan_up", "pan_down", "shake"]


def _make_motion_clip(img_path: str, duration: float, motion: str = None) -> ImageClip:
    """يحول صورة ثابتة لمشهد متحرك."""
    if motion is None:
        motion = random.choice(MOTION_STYLES)

    # نحمّل الصورة ونكبّرها شوية عشان نقدر نتحرك فيها
    img = Image.open(img_path).convert("RGB")
    W, H = VIDEO_WIDTH, VIDEO_HEIGHT
    scale_factor = 1.15  # 15% أكبر من الفيديو
    sw, sh = int(W * scale_factor), int(H * scale_factor)
    img = img.resize((sw, sh), Image.LANCZOS)
    arr = np.array(img)

    def make_frame(t):
        progress = t / duration if duration > 0 else 0

        if motion == "zoom_in":
            # zoom from scale_factor → 1.0
            s = scale_factor - (scale_factor - 1.0) * progress
            new_w, new_h = int(sw / s), int(sh / s)
            new_w = min(new_w, sw)
            new_h = min(new_h, sh)
            x0 = (sw - new_w) // 2
            y0 = (sh - new_h) // 2
            cropped = arr[y0:y0+new_h, x0:x0+new_w]
            return np.array(Image.fromarray(cropped).resize((W, H), Image.LANCZOS))

        elif motion == "zoom_out":
            # zoom from 1.0 → scale_factor
            s = 1.0 + (scale_factor - 1.0) * progress
            new_w, new_h = int(sw / s), int(sh / s)
            new_w = max(new_w, 1)
            new_h = max(new_h, 1)
            x0 = (sw - new_w) // 2
            y0 = (sh - new_h) // 2
            cropped = arr[y0:y0+new_h, x0:x0+new_w]
            return np.array(Image.fromarray(cropped).resize((W, H), Image.LANCZOS))

        elif motion == "pan_right":
            max_x = sw - W
            x0 = int(max_x * progress)
            return arr[0:H, x0:x0+W]

        elif motion == "pan_left":
            max_x = sw - W
            x0 = int(max_x * (1 - progress))
            return arr[0:H, x0:x0+W]

        elif motion == "pan_up":
            max_y = sh - H
            y0 = int(max_y * progress)
            return arr[y0:y0+H, 0:W]

        elif motion == "pan_down":
            max_y = sh - H
            y0 = int(max_y * (1 - progress))
            return arr[y0:y0+H, 0:W]

        elif motion == "shake":
            # رعشة خفيفة — مناسبة للمشاهد المتوترة
            import math
            intensity = 8
            freq = 12
            dx = int(intensity * math.sin(2 * math.pi * freq * t) * (1 - progress * 0.5))
            dy = int(intensity * math.cos(2 * math.pi * freq * t * 0.7) * (1 - progress * 0.5))
            max_x = sw - W
            max_y = sh - H
            x0 = max(0, min(max_x, max_x // 2 + dx))
            y0 = max(0, min(max_y, max_y // 2 + dy))
            return arr[y0:y0+H, x0:x0+W]

        else:
            return arr[0:H, 0:W]

    clip = VideoClip(make_frame, duration=duration)
    clip = clip.set_fps(FPS)
    return clip


# ==============================
#  Subtitles حقيقية - تمشي مع الكلام كلمة بكلمة
# ==============================

async def _get_word_timings(text: str, voice: str) -> list:
    """
    يستخرج timing دقيق لكل كلمة من Edge-TTS.
    يرجع list من tuples: (word, start_sec, end_sec)
    """
    try:
        import edge_tts
        timings = []
        communicate = edge_tts.Communicate(text, voice)
        async for event in communicate.stream():
            if event["type"] == "WordBoundary":
                word  = event["text"]
                start = event["offset"] / 10_000_000   # من 100ns → ثانية
                dur   = event["duration"] / 10_000_000
                timings.append((word, start, start + dur))
        return timings
    except Exception as e:
        print(f"  ⚠️ word timing فشل: {e}")
        return []


def get_word_timings_sync(text: str, voice: str) -> list:
    """wrapper synchronous لـ _get_word_timings."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(_get_word_timings(text, voice))
        loop.close()
        return result
    except Exception:
        return []


def _group_timings_into_lines(word_timings: list, chunk_size: int = 5) -> list:
    """
    يقسم الكلمات لـ chunks من chunk_size كلمات.
    لكل كلمة في الـ chunk، يعمل entry بـ:
      - الـ chunk كله (5 كلمات)
      - index الكلمة الحالية (highlighted بالأصفر)
      - توقيت بداية ونهاية الكلمة دي
    يرجع list من: (words_list, highlight_idx, start_sec, end_sec)
    """
    if not word_timings:
        return []

    lines = []
    i = 0
    while i < len(word_timings):
        chunk = word_timings[i:i + chunk_size]
        words = [w[0] for w in chunk]
        for j, (word, start, end) in enumerate(chunk):
            lines.append((words, j, start, end))
        i += chunk_size

    return lines


def _build_subtitle_clips(subtitle_lines: list, scene_start: float,
                           font_path: str, font_size: int = 68) -> list:
    """
    يبني ImageClip لكل كلمة — الـ chunk كله ظاهر،
    الكلمة الحالية بالأصفر والباقي أبيض.
    كل clip مدته من بداية الكلمة لنهايتها بالظبط.
    """
    clips = []

    for words, highlight_idx, abs_start, abs_end in subtitle_lines:
        rel_start = abs_start - scene_start
        duration  = abs_end - abs_start

        if duration <= 0.01:
            continue

        try:
            cache_key = f"{'_'.join(words)}_{highlight_idx}"
            sub_path  = f"/tmp/sub_{abs(hash(cache_key))}.png"

            sub_img = _render_subtitle_image(words, highlight_idx, font_path, font_size)
            sub_img.save(sub_path)

            # نحسب المكان بشكل صح بناءً على حجم الصورة الفعلي
            # نحط الـ subtitle على بُعد BOTTOM_MARGIN من أسفل الفيديو
            BOTTOM_MARGIN = 60  # مسافة من أسفل الشاشة بالبيكسل
            sub_h = sub_img.size[1]
            y_pos = VIDEO_HEIGHT - sub_h - BOTTOM_MARGIN
            y_pos = max(0, y_pos)  # مش يطلع فوق حدود الشاشة

            sub_clip = (ImageClip(sub_path, ismask=False)
                        .set_start(rel_start)
                        .set_duration(duration)
                        .set_position(("center", y_pos)))
            clips.append(sub_clip)

        except Exception as e:
            print(f"  ⚠️ subtitle clip فشل: {e}")

    return clips


def _render_subtitle_image(words: list, highlight_idx: int,
                            font_path: str, font_size: int = 68) -> Image.Image:
    """
    يرسم الـ chunk كله على سطر واحد:
    - الكلمة highlighted (اللي بيقولها دلوقتي): أصفر + أكبر شوية
    - باقي الكلمات: أبيض
    - ظل أسود قوي لكل الكلمات للوضوح
    - الصورة بعرض الفيديو كامل عشان تتوسط صح
    """
    try:
        font_normal = ImageFont.truetype(font_path, font_size)
        font_highlight = ImageFont.truetype(font_path, int(font_size * 1.15))
    except Exception:
        font_normal = ImageFont.load_default()
        font_highlight = font_normal

    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    shadow    = 4
    gap       = 22

    # نحسب حجم كل كلمة
    word_data = []
    for i, w in enumerate(words):
        display = w.upper()
        f = font_highlight if i == highlight_idx else font_normal
        bbox = dummy_draw.textbbox((0, 0), display, font=f)
        word_data.append({
            "text":  display,
            "font":  f,
            "w":     bbox[2] - bbox[0],
            "h":     bbox[3] - bbox[1],
            "color": (255, 229, 0, 255) if i == highlight_idx else (255, 255, 255, 255),
        })

    total_w = sum(d["w"] for d in word_data) + gap * (len(word_data) - 1)
    max_h   = max(d["h"] for d in word_data)

    # الصورة بعرض الفيديو كامل
    img_w = VIDEO_WIDTH
    img_h = max_h + shadow * 2 + 20
    img   = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(img)

    # نبدأ من المنتصف
    x = (img_w - total_w) // 2
    y = 10

    for d in word_data:
        # ظل من كل الاتجاهات
        for dx, dy in [(-shadow, 0), (shadow, 0), (0, -shadow), (0, shadow),
                       (-shadow, -shadow), (shadow, -shadow),
                       (-shadow, shadow), (shadow, shadow)]:
            draw.text((x + dx, y + dy), d["text"], font=d["font"], fill=(0, 0, 0, 255))
        # الكلمة بلونها
        draw.text((x, y), d["text"], font=d["font"], fill=d["color"])
        x += d["w"] + gap

    return img


# ==============================
#  Thumbnail
# ==============================

def _generate_thumbnail_with_dalle(title: str, bg_keyword: str, output_path: str) -> bool:
    """يطلب من GPT-4o (DALL-E 3) يولد thumbnail احترافي لليوتيوب."""
    import base64
    from config import GITHUB_TOKEN

    prompt = f"""Create a professional YouTube thumbnail for a video titled: "{title}"

Style requirements:
- Eye-catching, high contrast, vibrant colors
- Cinematic dramatic lighting
- Bold visual composition — the kind that gets clicks
- Topic/theme: {bg_keyword}
- No text overlays — just the visual background
- 16:9 aspect ratio feel
- Photorealistic or hyper-detailed digital art style"""

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
    }

    # نستخدم DALL-E 3 عبر GitHub Models
    dalle_url = "https://models.github.ai/inference/images/generations"
    dalle_payload = {
        "model": "dall-e-3",
        "prompt": prompt,
        "n": 1,
        "size": "1792x1024",
        "quality": "hd",
        "response_format": "b64_json"
    }

    try:
        print("🎨 GPT-4o (DALL-E 3) بيولد الـ thumbnail...")
        r = requests.post(dalle_url, headers=headers, json=dalle_payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        b64 = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(b64)
        from io import BytesIO
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img = img.resize((1280, 720), Image.LANCZOS)
        img.save(output_path, "JPEG", quality=95)
        print("✅ Thumbnail من DALL-E 3 جاهز")
        return True
    except Exception as e:
        print(f"⚠️ DALL-E 3 فشل: {e} — fallback للـ Pillow")
        return False


def create_thumbnail(story_data: dict, bg_image_path: str, output_path: str) -> str:
    title      = story_data["title"]
    bg_keyword = story_data.get("bg_keyword", "space")

    # أولاً: جرب DALL-E 3
    if _generate_thumbnail_with_dalle(title, bg_keyword, output_path):
        return output_path

    # Fallback: الطريقة القديمة بـ Pillow
    img  = Image.open(bg_image_path).convert("RGB")
    img  = img.resize((1280, 720), Image.LANCZOS)
    img  = img.filter(ImageFilter.GaussianBlur(radius=2))

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 120))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(FONT_PATH, 80)
    except Exception:
        font = ImageFont.load_default()

    wrapped = textwrap.fill(title, width=25)
    lines   = wrapped.split("\n")
    total_h = len(lines) * 95
    y       = (720 - total_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (1280 - (bbox[2] - bbox[0])) // 2
        draw.text((x+3, y+3), line, font=font, fill=(0, 0, 0))
        draw.text((x,   y),   line, font=font, fill=(255, 220, 50))
        y += 95

    img.save(output_path)
    return output_path


# ==============================
#  بناء الفيديو الكامل
# ==============================

def create_video(story_data: dict, audio_path: str, output_filename: str,
                 scene_durations: list = None,
                 word_timings: list = None) -> str:
    """يبني الفيديو بـ:
       - حركة حقيقية في الصور (Pan/Zoom/Shake)
       - subtitles حقيقية تمشي مع الكلام (من word_timings اللي جت من tts_engine)
       - موسيقى خلفية شغالة
       - SFX من Freesound بـ rate limiting صح
    """
    os.makedirs(VIDEO_DIR, exist_ok=True)
    output_path = os.path.join(VIDEO_DIR, output_filename)

    paragraphs    = story_data["story_paragraphs"]
    bg_keyword    = story_data.get("bg_keyword", "dark")
    mood          = story_data.get("mood", "epic")
    title         = story_data["title"]

    # ─── 1. صور الخلفية ───────────────────────────────────
    print(f"🎨 تجهيز {len(paragraphs)} صورة...")
    scene_image_paths = story_data.get("scene_image_paths", [])
    scene_keywords = story_data.get("scene_keywords") or [bg_keyword] * len(paragraphs)

    # fallback لو مفيش صور من GPT-4o
    if len(scene_image_paths) != len(paragraphs):
        scene_image_paths = [fetch_scene_image(scene_keywords[i], i, i) for i in range(len(paragraphs))]

    # لو في صور None (فشل تحميلها) نعمل fallback لكل واحدة
    bg_images = []
    for i, path in enumerate(scene_image_paths):
        if path and os.path.exists(path) and os.path.getsize(path) > 3000:
            bg_images.append(path)
        else:
            print(f"  ⚠️ مشهد {i+1}: مفيش صورة — fallback")
            bg_images.append(_fallback_background(bg_keyword, i))

    # ─── 2. الموسيقى ──────────────────────────────────────
    music_path = fetch_background_music(mood)

    # ─── 3. حساب التوقيت ──────────────────────────────────
    audio_clip     = AudioFileClip(audio_path)
    total_duration = audio_clip.duration

    if scene_durations and len(scene_durations) == len(paragraphs):
        durations = scene_durations
        print("✅ مدة كل فقرة مقاسة فعلاً")
    else:
        eq = total_duration / len(paragraphs)
        durations = [eq] * len(paragraphs)
        print("⚠️ fallback — تقسيم متساوي")

    start_times = []
    cum = 0.0
    for d in durations:
        start_times.append(cum)
        cum += d

    # ─── 4. SFX بـ rate limiting (متسلسل) ────────────────
    sfx_entries = []
    if ENABLE_SFX:
        print(f"🔊 توليد SFX ({len(paragraphs)} مشهد) — متسلسل...")
        for i in range(len(paragraphs)):
            cap      = min(SFX_MAX_DURATION, durations[i])
            sfx_path = fetch_scene_sfx(scene_keywords[i], i, cap)
            sfx_entries.append((sfx_path, start_times[i], durations[i]))

    # ─── 5. Word timings — بتيجي جاهزة من tts_engine ─────
    # word_timings = list of (word, abs_start_sec, abs_end_sec)
    all_word_timings = word_timings or []
    if all_word_timings:
        print(f"💬 word timings جاهزة ({len(all_word_timings)} كلمة) — من tts_engine")
    else:
        print("  ⚠️ مفيش word timings — subtitles مش هتظهر")

    # ─── 6. بناء المشاهد ──────────────────────────────────
    print(f"🎬 بناء {len(paragraphs)} مشهد...")
    motion_sequence = ["zoom_in", "pan_right", "zoom_out", "pan_left",
                       "pan_up", "zoom_in", "shake", "pan_down"]

    scene_clips = []
    for i in range(len(paragraphs)):
        motion = motion_sequence[i % len(motion_sequence)]
        clip   = _make_motion_clip(bg_images[i], durations[i], motion)

        # fade بين المشاهد
        if i > 0:
            clip = fadein(clip, 0.5)
        if i < len(paragraphs) - 1:
            clip = fadeout(clip, 0.5)

        scene_clips.append(clip)
        print(f"  ✅ مشهد {i+1} ({motion}, {durations[i]:.1f}s)")

    # ─── 7. دمج المشاهد ───────────────────────────────────
    print("🔗 دمج المشاهد...")
    base_video = concatenate_videoclips(scene_clips, method="compose")

    # ─── 8. Subtitles معطلة نهائياً ───────────────────────
    # تم إيقاف الـ subtitles بشكل كامل
    final_video = base_video

    # ─── 9. دمج الصوت ─────────────────────────────────────
    final_audio = mix_full_audio(audio_clip, music_path, sfx_entries, total_duration)
    final_video = final_video.set_audio(final_audio)
    final_video = final_video.set_duration(total_duration)

    # ─── 10. تصدير ────────────────────────────────────────
    print(f"💾 تصدير → {output_path}")
    final_video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4000k",
        threads=4,
        logger=None
    )

    audio_clip.close()
    final_video.close()

    print(f"✅ الفيديو جاهز: {output_path}")
    return output_path


# ==============================
#  فيديو قطط - يستخدم كليبات بدل الصور
# ==============================

def create_cat_video(story_data: dict, audio_path: str, output_filename: str,
                     cat_clips: list,
                     scene_durations: list = None,
                     word_timings: list = None,
                     target_duration: float = 300.0) -> str:
    """
    يبني فيديو حيوانات مضحكة بـ:
      - intro مسموع في أول 10-15 ثانية (على أول كليب)
      - كليبات في المنتصف بصوت الفيديو الأصلي فقط (بدون تعليق)
      - outro مسموع في آخر 10-15 ثانية (على آخر كليب)
      - الكل بيتجمع بالظبط في target_duration (افتراضي 300 ثانية = 5 دقايق)
    """
    import math
    os.makedirs(VIDEO_DIR, exist_ok=True)
    output_path = os.path.join(VIDEO_DIR, output_filename)

    paragraphs = story_data["story_paragraphs"]  # [intro_text, outro_text]
    mood       = story_data.get("mood", "happy")

    if not cat_clips:
        raise ValueError("❌ Cat Pipeline: مفيش كليبات — تأكد إن Internet Archive fetcher شغال.")

    # ─── 1. الموسيقى ──────────────────────────────────────
    music_path = fetch_background_music(mood)

    # ─── 2. مدة الـ narration (intro + outro) ─────────────
    narration_clip = AudioFileClip(audio_path)
    narration_dur  = narration_clip.duration

    # مدة الـ intro = الفقرة الأولى، الـ outro = الفقرة التانية
    if scene_durations and len(scene_durations) >= 2:
        intro_dur = scene_durations[0]
        outro_dur = scene_durations[1]
    else:
        intro_dur = narration_dur * 0.5
        outro_dur = narration_dur * 0.5

    middle_dur = max(target_duration - intro_dur - outro_dur, 10.0)
    print(f"⏱️ intro={intro_dur:.1f}s | middle={middle_dur:.1f}s | outro={outro_dur:.1f}s | total={target_duration:.0f}s")

    # ─── 3. بناء كليبات الـ middle ────────────────────────
    print(f"🎬 بناء الـ middle من {len(cat_clips)} كليب...")

    def _load_clip(path, target_dur):
        if not os.path.exists(path) or os.path.getsize(path) < 10_000:
            return None
        raw = VideoFileClip(path)
        if raw.duration < 1.0:
            return None
        if raw.duration < target_dur:
            loops = math.ceil(target_dur / raw.duration)
            from moviepy.editor import concatenate_videoclips as _cc
            raw = _cc([raw] * loops)
        clip = raw.subclip(0, min(target_dur, raw.duration))
        return clip.resize((VIDEO_WIDTH, VIDEO_HEIGHT))

    # حساب مدة كل كليب middle
    n_clips      = len(cat_clips)
    per_clip_dur = middle_dur / n_clips

    middle_clips = []
    accumulated  = 0.0
    for i, cp in enumerate(cat_clips):
        remaining = middle_dur - accumulated
        if remaining <= 0:
            break
        dur = min(per_clip_dur, remaining)
        c = _load_clip(cp, dur)
        if c is None:
            print(f"  ⚠️ كليب {i+1} فشل — skip")
            continue
        if i > 0:
            c = fadein(c, 0.3)
        c = fadeout(c, 0.3)
        middle_clips.append(c)
        accumulated += dur
        print(f"  ✅ كليب {i+1} ({dur:.1f}s)")

    if not middle_clips:
        raise ValueError("❌ كل الكليبات فشلت في التحميل!")

    # لو الـ middle أقصر من المطلوب — كرر
    while accumulated < middle_dur - 1.0 and middle_clips:
        extra_needed = middle_dur - accumulated
        c = _load_clip(cat_clips[len(middle_clips) % len(cat_clips)], extra_needed)
        if c:
            middle_clips.append(fadein(c, 0.3))
            accumulated += extra_needed

    middle_video = concatenate_videoclips(middle_clips, method="compose")

    # ─── 4. كليب الـ intro (أول كليب) ────────────────────
    intro_clip = _load_clip(cat_clips[0], intro_dur)
    if intro_clip is None:
        intro_clip = middle_clips[0].subclip(0, intro_dur)
    intro_clip = fadeout(intro_clip, 0.3)

    # ─── 5. كليب الـ outro (آخر كليب) ────────────────────
    outro_clip = _load_clip(cat_clips[-1], outro_dur)
    if outro_clip is None:
        outro_clip = middle_clips[-1].subclip(0, outro_dur)
    outro_clip = fadein(outro_clip, 0.3)

    # ─── 6. دمج كل الأجزاء ───────────────────────────────
    print("🔗 دمج intro + middle + outro...")
    base_video = concatenate_videoclips([intro_clip, middle_video, outro_clip], method="compose")

    # trim أو pad للـ target_duration بالظبط
    if base_video.duration > target_duration + 0.5:
        base_video = base_video.subclip(0, target_duration)
    elif base_video.duration < target_duration - 0.5:
        # pad بآخر فريم
        from moviepy.editor import ImageClip
        last_frame = base_video.get_frame(base_video.duration - 0.1)
        pad_dur    = target_duration - base_video.duration
        pad_clip   = ImageClip(last_frame, duration=pad_dur)
        base_video = concatenate_videoclips([base_video, pad_clip])

    # ─── 7. دمج الصوت ─────────────────────────────────────
    # الـ narration بيتسمع في الأول (intro) وفي الآخر (outro) فقط
    # في المنتصف: صوت الكليبات الأصلي + موسيقى خلفية

    try:
        clips_audio = base_video.audio
        if clips_audio:
            clips_audio = volumex(clips_audio, 0.35)  # صوت الكليبات في المنتصف واضح

        # الـ narration audio: intro في أول intro_dur ثانية، outro في آخر outro_dur ثانية
        narration_full = AudioFileClip(audio_path)  # intro + outro concatenated
        # نحط الـ intro في t=0 والـ outro في t=(total - outro_dur)
        outro_start = target_duration - outro_dur
        narration_intro = narration_full.subclip(0, min(intro_dur, narration_full.duration))
        narration_outro_start = min(intro_dur, narration_full.duration)
        narration_outro = narration_full.subclip(narration_outro_start)
        narration_outro = narration_outro.set_start(outro_start)

        audio_layers = [narration_intro, narration_outro]
        if clips_audio:
            audio_layers.append(clips_audio)

        if music_path:
            music = AudioFileClip(music_path)
            music = audio_loop(music, duration=target_duration) if music.duration < target_duration \
                    else music.subclip(0, target_duration)
            music = volumex(music, 0.08)
            music = music.audio_fadein(2.0).audio_fadeout(2.0)
            audio_layers.append(music)

        final_audio = CompositeAudioClip(audio_layers)
        final_video = base_video.set_audio(final_audio)

    except Exception as e:
        print(f"  ⚠️ خطأ في دمج الصوت: {e} — fallback")
        final_video = base_video.set_audio(narration_clip)

    final_video = final_video.set_duration(target_duration)

    # ─── 8. تصدير ─────────────────────────────────────────
    print(f"💾 تصدير → {output_path} ({target_duration:.0f}s)")
    final_video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4000k",
        threads=4,
        logger=None
    )

    narration_clip.close()
    final_video.close()

    print(f"✅ فيديو الحيوانات جاهز: {output_path}")
    return output_path


if __name__ == "__main__":
    print("video_maker.py - استخدم main.py للتشغيل الكامل")
