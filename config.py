# config.py

# API Keys
MISTRAL_API_KEY = "ILVFFVrVxU3Zt4JxVtYqAE7ZsXXjVeFI"
MISTRAL_MODEL   = "mistral-small-2506"
STORY_MAX_WORDS = 600

# Freesound API
FREESOUND_API_KEY = "VpGovv94RUISeahonKXaYtxy1IOaL6JoS86bsAWP"

# Video Settings
VIDEO_WIDTH      = 1920
VIDEO_HEIGHT     = 1080
FPS              = 24
FONT_PATH        = "assets/fonts/arabic.ttf"
FONT_SIZE_STORY  = 52
FONT_SIZE_TITLE  = 72
TEXT_COLOR       = "white"
SHADOW_COLOR     = "black"
IMAGE_DURATION   = 8

# TTS - Edge-TTS (مجاني، بدون API key)
TTS_VOICE    = "en-US-GuyNeural"   # صوت سرد عميق
TTS_LANGUAGE = "en"
TTS_SPEED    = 1.0

# Background Music (Freesound)
MUSIC_DIR          = "output/music"
MUSIC_VOLUME       = 0.12
MUSIC_FADE_SECONDS = 2.0

# Sound Effects (Freesound)
ENABLE_SFX      = True
SFX_DIR         = "output/sfx"
SFX_VOLUME      = 0.35
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
