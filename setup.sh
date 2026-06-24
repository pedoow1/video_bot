#!/bin/bash
# setup.sh - تنصيب كل المتطلبات دفعة واحدة

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     Story Video Bot - Setup 🚀       ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ─── Termux packages ──────────────────────────
echo "📦 [1/3] تنصيب Termux packages..."
pkg update -y && pkg upgrade -y
pkg install -y python ffmpeg git

# ─── Python packages ──────────────────────────
echo ""
echo "🐍 [2/3] تنصيب Python packages..."
pip install --upgrade pip

pip install \
    requests \
    moviepy \
    Pillow \
    edge-tts \
    google-api-python-client \
    google-auth-httplib2 \
    google-auth-oauthlib \
    schedule \
    numpy

# Kokoro TTS (اختياري - محلي بدون نت)
echo ""
echo "🎙️ تنصيب edge-tts (TTS عربي)..."
pip install edge-tts

# ─── خط عربي ──────────────────────────────────
echo ""
echo "🔤 [3/3] تحميل خط عربي..."
mkdir -p assets/fonts

FONT_URL="https://github.com/google/fonts/raw/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf"
curl -L "$FONT_URL" -o assets/fonts/arabic.ttf 2>/dev/null

if [ -f "assets/fonts/arabic.ttf" ]; then
    echo "   ✅ خط Cairo العربي محمّل"
else
    echo "   ⚠️  فشل تحميل الخط، جرب يدوياً:"
    echo "   curl -L 'https://github.com/google/fonts/raw/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf' -o assets/fonts/arabic.ttf"
fi

# ─── مجلدات الإخراج ───────────────────────────
mkdir -p output/audio output/videos output/images

# ─── ملف الإعدادات ────────────────────────────
echo ""
echo "⚙️  إعداد config.py..."
if [ ! -f "config.py" ]; then
    echo "   ✅ config.py موجود"
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║         التنصيب اكتمل ✅             ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "الخطوات التالية:"
echo ""
echo "1️⃣  عدّل config.py وحط الـ API Keys:"
echo "    - MISTRAL_API_KEY  → console.mistral.ai"
echo "    - UNSPLASH_ACCESS_KEY → unsplash.com/developers"
echo ""
echo "2️⃣  حط ملف client_secrets.json من Google Cloud Console"
echo "    console.cloud.google.com → APIs → YouTube Data API v3"
echo ""
echo "3️⃣  شغّل البوت:"
echo "    python main.py --test          # اختبار بدون رفع"
echo "    python main.py --now           # انشر فيديو دلوقتي"
echo "    python main.py --schedule      # جدول يومي أوتوماتيك"
echo ""
