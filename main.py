import os
import sys
import argparse
from datetime import datetime
from video_fetcher import run_cat_pipeline

def main():
    parser = argparse.ArgumentParser(description="Story Video Bot")
    parser.add_argument('--now', action='store_true', help="تشغيل فوري")
    parser.add_argument('--cats', action='store_true', help="عمل فيديو قطط")
    parser.add_argument('--topic', type=str, help="موضوع مخصص")
    parser.add_argument('--test', action='store_true', help="تجربة بدون رفع")
    
    args = parser.parse_args()

    print(f"\n🎥 Story Video Bot - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    success = False

    if args.cats:
        print("🐱 تشغيل وضع القطط...")
        success = run_cat_pipeline()
    elif args.topic:
        print(f"📝 تشغيل موضوع: {args.topic}")
        # هنا يمكن إضافة دالة لمواضيع أخرى لاحقًا
        success = run_cat_pipeline()  # مؤقتًا
    else:
        # الوضع الافتراضي
        print("🐱 تشغيل الوضع الافتراضي (Cats)")
        success = run_cat_pipeline()

    if success:
        print("\n✅ تم الانتهاء بنجاح!")
        if not args.test:
            print("📤 جاري الرفع إلى YouTube (لو اليوploader شغال)...")
            # هنا هنضيف youtube_uploader لاحقًا
    else:
        print("\n❌ فشل في إنتاج الفيديو")

    print("=" * 60)

if __name__ == "__main__":
    main()
