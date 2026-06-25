# main.py - التشغيل الكامل الأوتوماتيك

import os
import time
import schedule
import argparse
from datetime import datetime
from story_generator  import generate_story, generate_scene_descriptions, generate_cat_script
from tts_engine       import text_to_speech_paragraphs
from image_fetcher    import get_scene_images
from video_fetcher    import fetch_cat_clips
from video_maker      import create_video, create_cat_video, create_thumbnail, fetch_background_images
from youtube_uploader import upload_video
from config           import UPLOAD_SCHEDULE_HOUR, STORIES_PER_DAY, OUTPUT_DIR


def run_pipeline(topic: str = None):
    """خط إنتاج فيديو واحد من البداية للنهاية"""

    start_time = time.time()
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "="*55)
    print(f"  🎬 بدء إنتاج فيديو جديد - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*55 + "\n")

    try:
        # ─── الخطوة 1: توليد القصة ───────────────────────
        print("📝 [1/4] توليد القصة بـ Mistral...")
        story = generate_story(topic)
        print(f"   العنوان: {story['title']}")

        # ─── الخطوة 2: تحويل النص لصوت ──────────────────
        print("\n🎙️ [2/4] تحويل النص لصوت...")
        audio_filename = f"audio_{timestamp}.wav"
        audio_info     = text_to_speech_paragraphs(story["story_paragraphs"], audio_filename)
        audio_path     = audio_info["audio_path"]
        duration       = audio_info["total_duration"]
        print(f"   مدة الصوت: {duration:.0f} ثانية ({duration/60:.1f} دقيقة)")

        # ─── الخطوة 2.5: وصف المشاهد + جلب الصور بـ GPT-4o ─
        print("\n🎨 [2.5/4] توليد أوصاف المشاهد...")
        scene_descriptions = generate_scene_descriptions(
            story["story_paragraphs"],
            story["title"]
        )

        print("\n🖼️ GPT-4o بيجيب الصور...")
        scene_image_paths = get_scene_images(scene_descriptions)
        story["scene_image_paths"] = scene_image_paths

        # ─── الخطوة 3: صناعة الفيديو ──────────────────────
        print("\n🎬 [3/4] صناعة الفيديو...")
        video_filename = f"video_{timestamp}.mp4"
        video_path     = create_video(story, audio_path, video_filename,
                                       scene_durations=audio_info["durations"],
                                       word_timings=audio_info.get("word_timings", []))

        # Thumbnail
        bg_images       = fetch_background_images(story.get("bg_keyword", "dark"), count=1)
        thumbnail_path  = os.path.join(OUTPUT_DIR, f"thumb_{timestamp}.jpg")
        create_thumbnail(story, bg_images[0], thumbnail_path)

        # ─── الخطوة 4: رفع على YouTube ───────────────────
        print("\n📤 [4/4] رفع على YouTube...")
        video_id = upload_video(video_path, story, thumbnail_path)

        # ─── ملخص ─────────────────────────────────────────
        elapsed = time.time() - start_time
        print("\n" + "="*55)
        print(f"  ✅ انتهى في {elapsed/60:.1f} دقيقة")
        print(f"  🔗 https://youtube.com/watch?v={video_id}")
        print("="*55 + "\n")

        log_video(story, video_id, elapsed)
        return video_id

    except Exception as e:
        print(f"\n❌ فشل Pipeline: {e}")
        import traceback
        traceback.print_exc()
        return None


def run_cat_pipeline(topic: str = None):
    """خط إنتاج فيديو قطط مضحكة من البداية للنهاية"""

    start_time = time.time()
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("\n" + "="*55)
    print(f"  🐱 بدء إنتاج فيديو قطط - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*55 + "\n")

    try:
        # ─── الخطوة 1: توليد السكريبت ─────────────────────
        print("📝 [1/4] توليد سكريبت القطط بـ Mistral...")
        story = generate_cat_script(topic)
        print(f"   العنوان: {story['title']}")

        # ─── الخطوة 2: تحويل النص لصوت ──────────────────
        print("\n🎙️ [2/4] تحويل النص لصوت...")
        audio_filename = f"audio_cats_{timestamp}.wav"
        audio_info     = text_to_speech_paragraphs(story["story_paragraphs"], audio_filename)
        audio_path     = audio_info["audio_path"]
        duration       = audio_info["total_duration"]
        print(f"   مدة الصوت: {duration:.0f} ثانية ({duration/60:.1f} دقيقة)")

        # ─── الخطوة 3: تحميل كليبات القطط ───────────────
        print("\n🐱 [3/4] جلب كليبات قطط من يوتيوب...")
        cat_clips = fetch_cat_clips(count=len(story["story_paragraphs"]))

        # ─── الخطوة 4: صناعة الفيديو ─────────────────────
        print("\n🎬 [4/4] صناعة الفيديو...")
        video_filename = f"cats_{timestamp}.mp4"
        video_path     = create_cat_video(
            story, audio_path, video_filename,
            cat_clips=cat_clips,
            scene_durations=audio_info["durations"],
            word_timings=audio_info.get("word_timings", [])
        )

        # Thumbnail
        thumbnail_path = os.path.join(OUTPUT_DIR, f"thumb_cats_{timestamp}.jpg")
        if cat_clips:
            # استخدم أول فريم من أول كليب كـ thumbnail
            import subprocess
            subprocess.run([
                "ffmpeg", "-y", "-i", cat_clips[0],
                "-ss", "1", "-vframes", "1",
                "-vf", "scale=1280:720",
                thumbnail_path
            ], capture_output=True)
        if not os.path.exists(thumbnail_path):
            bg_images = fetch_background_images("cats", count=1)
            create_thumbnail(story, bg_images[0], thumbnail_path)

        # ─── رفع على YouTube ──────────────────────────────
        print("\n📤 رفع على YouTube...")
        video_id = upload_video(video_path, story, thumbnail_path)

        elapsed = time.time() - start_time
        print("\n" + "="*55)
        print(f"  ✅ انتهى في {elapsed/60:.1f} دقيقة")
        print(f"  🔗 https://youtube.com/watch?v={video_id}")
        print("="*55 + "\n")

        log_video(story, video_id, elapsed)
        return video_id

    except Exception as e:
        print(f"\n❌ فشل Cat Pipeline: {e}")
        import traceback
        traceback.print_exc()
        return None


(story: dict, video_id: str, elapsed: float):
    """يحفظ سجل بكل الفيديوهات اللي اتنشرت"""
    log_path = os.path.join(OUTPUT_DIR, "videos_log.txt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | "
                f"https://youtube.com/watch?v={video_id} | "
                f"{story['title']} | "
                f"{elapsed/60:.1f} دقيقة\n")


def scheduled_job():
    """الوظيفة المجدولة - بتشتغل كل يوم"""
    print(f"⏰ تشغيل مجدول - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    for i in range(STORIES_PER_DAY):
        if i > 0:
            print(f"⏳ انتظار 5 دقائق قبل الفيديو التالي...")
            time.sleep(300)
        run_pipeline()


def setup_scheduler():
    """إعداد الجدول اليومي"""
    schedule_time = f"{UPLOAD_SCHEDULE_HOUR:02d}:00"
    schedule.every().day.at(schedule_time).do(scheduled_job)
    print(f"⏰ الجدول شغال - هينشر كل يوم الساعة {schedule_time}")
    print("   اضغط Ctrl+C للإيقاف\n")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Story Video Bot 🎬")

    parser.add_argument("--now", action="store_true", help="اعمل وانشر فيديو دلوقتي")
    parser.add_argument("--cats", action="store_true", help="اعمل فيديو قطط مضحكة")
    parser.add_argument("--topic", type=str, default=None, help='موضوع القصة أو القطط')
    parser.add_argument("--schedule", action="store_true", help="شغّل الجدول الأوتوماتيك اليومي")
    parser.add_argument("--test", action="store_true", help="اختبار بدون رفع YouTube")

    args = parser.parse_args()

    if args.test:
        print("🧪 وضع الاختبار (بدون رفع)\n")
        story      = generate_story(args.topic)
        audio_info = text_to_speech_paragraphs(story["story_paragraphs"], "test_audio.wav")

        print("\n🎨 توليد برومبتات الصور...")
        scene_keywords = generate_scene_descriptions(
            story["story_paragraphs"],
            story["title"]
        )
        story["scene_keywords"] = scene_keywords

        video = create_video(story, audio_info["audio_path"], "test_video.mp4",
                              scene_durations=audio_info["durations"],
                              word_timings=audio_info.get("word_timings", []))
        print(f"\n✅ الفيديو جاهز: {video}")

    elif args.cats:
        run_cat_pipeline(args.topic)

    elif args.now:
        run_pipeline(args.topic)

    elif args.schedule:
        setup_scheduler()

    else:
        parser.print_help()
        print("\n💡 أمثلة:")
        print('  python main.py --now')
        print('  python main.py --now --topic "10 facts about Mars"')
        print('  python main.py --cats')
        print('  python main.py --cats --topic "cats vs dogs"')
        print('  python main.py --schedule')
        print('  python main.py --test')
