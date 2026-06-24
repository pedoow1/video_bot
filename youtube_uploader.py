# youtube_uploader.py - رفع الفيديو على YouTube

import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # لازم يكون أول سطر

import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ==============================
#  الإعدادات
# ==============================
YOUTUBE_CLIENT_SECRETS = "client_secrets.json"
YOUTUBE_TOKEN          = "youtube_token.json"
YOUTUBE_SCOPES         = ["https://www.googleapis.com/auth/youtube.upload"]


# ==============================
#  المصادقة
# ==============================

def get_youtube_service():
    """يسجل دخول YouTube ويرجع الـ service"""
    creds = None

    # لو عندنا token محفوظ من قبل
    if os.path.exists(YOUTUBE_TOKEN):
        try:
            creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN, YOUTUBE_SCOPES)
            print("✅ تم تحميل الـ token المحفوظ")
        except Exception as e:
            print(f"⚠️ الـ token القديم خربان: {e}")
            creds = None

    # لو محتاج مصادقة جديدة
    if not creds or not creds.valid:

        if not os.path.exists(YOUTUBE_CLIENT_SECRETS):
            print("❌ ملف client_secrets.json مش موجود!")
            print("   روح: console.cloud.google.com")
            print("   APIs & Services → Credentials → Create OAuth 2.0 Client ID")
            print("   حمّل الـ JSON وسميه client_secrets.json")
            raise FileNotFoundError("client_secrets.json مش موجود")

        print("\n" + "="*50)
        print("  مصادقة YouTube")
        print("="*50)

        flow = InstalledAppFlow.from_client_secrets_file(
            YOUTUBE_CLIENT_SECRETS,
            YOUTUBE_SCOPES
        )

        # شغّل سيرفر محلي على port 8080
        creds = flow.run_local_server(
            port=8080,
            prompt="consent",
            access_type="offline"
        )

        # حفظ الـ token للمرات الجاية
        with open(YOUTUBE_TOKEN, "w") as f:
            f.write(creds.to_json())
        print("✅ تم حفظ الـ token - مش هتحتاج تعمل ده تاني")

    return build("youtube", "v3", credentials=creds)


# ==============================
#  رفع الفيديو
# ==============================

def upload_video(video_path: str, story: dict, thumbnail_path: str = None) -> str:
    """يرفع الفيديو على YouTube ويرجع الـ video ID"""

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"الفيديو مش موجود: {video_path}")

    file_size = os.path.getsize(video_path) / (1024 * 1024)
    print(f"\n📤 جاري رفع الفيديو... ({file_size:.1f} MB)")

    youtube = get_youtube_service()

    # بيانات الفيديو
    body = {
        "snippet": {
            "title":       story["title"],
            "description": build_description(story),
            "tags":        story.get("tags", []),
            "categoryId":  "22",               # People & Blogs
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":          "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5  # 5MB chunks
    )

    try:
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        # رفع تدريجي مع شريط تقدم
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
                print(f"\r  [{bar}] {percent}%", end="", flush=True)

        print()  # سطر جديد بعد شريط التقدم

        video_id  = response["id"]
        video_url = f"https://youtube.com/watch?v={video_id}"

        print(f"✅ تم الرفع بنجاح!")
        print(f"🔗 الرابط: {video_url}")

        # رفع الـ thumbnail لو موجود
        if thumbnail_path and os.path.exists(thumbnail_path):
            upload_thumbnail(youtube, video_id, thumbnail_path)

        return video_id

    except HttpError as e:
        print(f"❌ خطأ من YouTube API: {e}")
        if e.resp.status == 403:
            print("   تأكد إن YouTube Data API v3 مفعّل في Google Cloud Console")
        raise


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str):
    """يرفع thumbnail للفيديو"""
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
        ).execute()
        print("🖼️ تم رفع الـ thumbnail")
    except Exception as e:
        print(f"⚠️ فشل رفع الـ thumbnail: {e}")


def build_description(story: dict) -> str:
    """يبني وصف YouTube من بيانات القصة"""
    desc = story.get("description", "")

    desc += "\n\n" + "─" * 30
    desc += "\n\n📖 Daily short stories - Subscribe and hit the bell 🔔"

    # إضافة الـ tags كـ hashtags
    tags = story.get("tags", [])
    if tags:
        hashtags = " ".join([f"#{t.replace(' ', '_')}" for t in tags[:5]])
        desc += f"\n\n{hashtags}"

    return desc[:5000]  # YouTube حد أقصى 5000 حرف


# ==============================
#  تشغيل مباشر للمصادقة
# ==============================

if __name__ == "__main__":
    print("🔐 جاري المصادقة مع YouTube...")
    youtube = get_youtube_service()
    print("✅ المصادقة تمت بنجاح!")
    print("   youtube_token.json اتحفظ — مش هتحتاج تعمل ده تاني")
