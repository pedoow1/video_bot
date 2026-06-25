# config.py

import os

# API Keys - بتيجي من GitHub Secrets أو environment variables
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_MODEL   = "mistral-small-2506"
STORY_MAX_WORDS = 600

# Freesound API
FREESOUND_API_KEY = os.environ.get("FREESOUND_API_KEY", "")

# Pexels API (قديم - مش بيستخدم)
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

# GitHub Token - لاستخدام GPT-4o عبر GitHub Models
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")

# YouTube Token - بييجي من GitHub Secret كـ JSON string
YOUTUBE_TOKEN_JSON = os.environ.get("YOUTUBE_TOKEN", "")

# Video Settings
VIDEO_WIDTH      = 1920
VIDEO_HEIGHT     = 1080
FPS              = 24
FONT_PATH        = "assets/fonts/arabic.ttf"
FONT_SIZE_STORY  = 52
FONT_SIZE_TITLE  = 72
TEXT_COLOR       = "white"
SHADOW_COLOR     = "black"
IMAGE_DURATION   = 10   # كل حقيقة بتاخد وقت أكتر شوية من القصص

# TTS - Edge-TTS (مجاني، بدون API key)
# صوت إنجليزي energetic مناسب لـ "10 Amazing Facts" content
TTS_VOICE    = "en-US-ChristopherNeural"   # صوت قوي ومقنع زي قنوات Facts
TTS_LANGUAGE = "en"
TTS_SPEED    = 1.0

# Background Music (Freesound)
MUSIC_DIR          = "output/music"
MUSIC_VOLUME       = 0.12
MUSIC_FADE_SECONDS = 2.0

# Sound Effects (Freesound)
ENABLE_SFX       = False
SFX_DIR          = "output/sfx"
SFX_VOLUME       = 0.35
SFX_MAX_DURATION = 5.0

# Schedule
UPLOAD_SCHEDULE_HOUR = 18
STORIES_PER_DAY      = 1

# YouTube
YT_CATEGORY_ID   = "22"
YT_PRIVACY       = "public"
YT_MADE_FOR_KIDS = False

# Dirs
OUTPUT_DIR = "output"
AUDIO_DIR  = "output/audio"
VIDEO_DIR  = "output/videos"
IMAGES_DIR = "output/images"
