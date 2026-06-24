# youtube_uploader.py - رفع الفيديو على YouTube

import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

YOUTUBE_TOKEN   = "youtube_token.json"
YOUTUBE_SCOPES  = ["https://www.googleapis.com/auth/youtube.upload"]


def get_youtube_service():
    """يسجل دخول YouTube ويرجع الـ service"""
    creds = None

    # ─── أولاً: جرب من Environment Variable (GitHub Actions) ───
    token_json = os.environ.get("YOUTUBE_TOKEN", "")
    if token_json:
        try:
            token_data = json.loads(token_json)
            creds = Credentials.from_authorized_user_info(token_data, YOUTUBE_SCOPES)
            print("✅ تم تحميل YouTube token من Environment Variable")
        except Exception as e:
            print(f"⚠️ فشل تحميل token من env: {e}")
            creds = None

    # ─── ثانياً: جرب من ملف محلي ───────────────────────────────
    if not creds and os.path.exists(YOUTUBE_TOKEN):
        try:
            creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN, YOUTUBE_SCOPES)
            print("✅ تم تحميل الـ token المحفوظ")
        except Exception as e:
            print(f"⚠️ الـ token القديم خربان: {e}")
            creds = None

    if not creds or not creds.valid:
        raise RuntimeError(
            "❌ مفيش YouTube token صالح!\n"
            "   - في GitHub: ضيف YOUTUBE_TOKEN في Secrets\n"
            "   - محلياً: شغّل python youtube_uploader.py مرة واحدة"
        )

    return build("youtube", "v3", credentials=creds)


def upload_video(video_path: str, story: dict, thumbnail_path: str = None) -> str:
    """يرفع الفيديو على YouTube ويرجع الـ video ID"""

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"الفيديو مش موجود: {video_path}")

    file_size = os.path.getsize(video_path) / (1024 * 1024)
    print(f"\n📤 جاري رفع الفيديو... ({file_size:.1f} MB)")

    youtube = get_youtube_service()

    body = {
        "snippet": {
            "title":           story["title"],
            "description":     build_description(story),
            "tags":            story.get("tags", []),
            "categoryId":      "22",
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":           "public",
            "selfDeclaredMadeForKids": False,
        }
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5
    )

    try:
        request  = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None

        while response is None:
            status, response = request.next_chunk()
            if status:
                percent = int(status.progress() * 100)
                bar = "█" * (percent // 5) + "░" * (20 - percent // 5)
                print(f"\r  [{bar}] {percent}%", end="", flush=True)

        print()

        video_id  = response["id"]
        video_url = f"https://youtube.com/watch?v={video_id}"
        print(f"✅ تم الرفع بنجاح!")
        print(f"🔗 الرابط: {video_url}")

        if thumbnail_path and os.path.exists(thumbnail_path):
            upload_thumbnail(youtube, video_id, thumbnail_path)

        return video_id

    except HttpError as e:
        print(f"❌ خطأ من YouTube API: {e}")
        if e.resp.status == 403:
            print("   تأكد إن YouTube Data API v3 مفعّل في Google Cloud Console")
        raise


def upload_thumbnail(youtube, video_id: str, thumbnail_path: str):
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
        ).execute()
        print("🖼️ تم رفع الـ thumbnail")
    except Exception as e:
        print(f"⚠️ فشل رفع الـ thumbnail: {e}")


def build_description(story: dict) -> str:
    desc = story.get("description", "")
    desc += "\n\n" + "─" * 30
    desc += "\n\n📖 Daily short stories - Subscribe and hit the bell 🔔"
    tags = story.get("tags", [])
    if tags:
        hashtags = " ".join([f"#{t.replace(' ', '_')}" for t in tags[:5]])
        desc += f"\n\n{hashtags}"
    return desc[:5000]


if __name__ == "__main__":
    print("🔐 جاري المصادقة مع YouTube...")
    youtube = get_youtube_service()
    print("✅ المصادقة تمت بنجاح!")
