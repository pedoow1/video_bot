# image_fetcher.py - GPT-4o (GitHub Models) يجيب روابط صور حقيقية

import json
import re
import os
import requests
from config import GITHUB_TOKEN, IMAGES_DIR

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"


def fetch_image_urls_with_gpt(scene_descriptions: list) -> list:
    """
    بيبعت وصف كل مشهد لـ GPT-4o عبر GitHub Models،
    وهو يدور على الإنترنت ويرجع رابط صورة حقيقية لكل مشهد.
    """

    scenes_text = "\n\n".join(
        f"[Scene {i+1}]: {desc}" for i, desc in enumerate(scene_descriptions)
    )

    prompt = f"""You are an expert at finding real, high-quality images online for YouTube fact videos.

For each scene below, find ONE real image URL that:
- Directly shows what the scene is describing (the actual subject, not a random related image)
- Is a direct link to a real image file (.jpg, .jpeg, .png, .webp)
- Comes from reliable sources: NASA, Wikipedia Commons, National Geographic, BBC, Reuters, AP, scientific institutions, or major news sites
- Is high resolution (at least 800x600)
- Is NOT a thumbnail, icon, logo, or watermarked stock photo

Scenes:
{scenes_text}

Reply with JSON ONLY in this exact shape:
{{"images": [
  {{"scene": 1, "url": "https://...", "source": "NASA"}},
  {{"scene": 2, "url": "https://...", "source": "Wikipedia"}},
  ...
]}}

Exactly {len(scene_descriptions)} items. Real URLs only — no placeholders."""

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.3,
    }

    print(f"🔍 GPT-4o بيدور على {len(scene_descriptions)} صورة...")

    for attempt in range(3):
        try:
            response = requests.post(GITHUB_MODELS_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            raw = re.sub(r"```json|```", "", raw).strip()

            data = json.loads(raw)
            images = data.get("images", [])

            if len(images) == len(scene_descriptions):
                urls = [img["url"] for img in images]
                for i, img in enumerate(images):
                    print(f"   مشهد {i+1}: {img['source']} — {img['url'][:60]}...")
                return urls
            else:
                print(f"⚠️ محاولة {attempt+1}: رجع {len(images)} بدل {len(scene_descriptions)} — retry")
                continue

        except Exception as e:
            print(f"⚠️ محاولة {attempt+1} فشلت: {e} — retry")
            continue

    raise RuntimeError("fetch_image_urls_with_gpt فشل بعد 3 محاولات")


def download_scene_images(urls: list, scene_descriptions: list) -> list:
    """
    يحمل الصور من الروابط اللي جابها GPT-4o.
    لو رابط فشل يرجع None ويكمل.
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)

    dl_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }

    paths = []
    for i, (url, desc) in enumerate(zip(urls, scene_descriptions)):
        safe = "".join(c if c.isalnum() else "_" for c in desc[:30])
        img_path = os.path.join(IMAGES_DIR, f"scene_{i+1}_{safe}.jpg")

        # لو موجودة خليها
        if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
            print(f"  ✅ مشهد {i+1}: موجودة")
            paths.append(img_path)
            continue

        try:
            print(f"  ⬇️ مشهد {i+1}: بيتحمل...")
            r = requests.get(url, headers=dl_headers, timeout=30, allow_redirects=True)

            if r.status_code != 200 or len(r.content) < 3000:
                print(f"  ❌ مشهد {i+1}: فشل (status {r.status_code})")
                paths.append(None)
                continue

            with open(img_path, "wb") as f:
                f.write(r.content)

            print(f"  ✅ مشهد {i+1}: جاهزة")
            paths.append(img_path)

        except Exception as e:
            print(f"  ❌ مشهد {i+1}: خطأ — {e}")
            paths.append(None)

    return paths


def get_scene_images(scene_descriptions: list) -> list:
    """
    الدالة الرئيسية — تجيب وصف المشاهد وترجع paths للصور المحملة.
    """
    urls = fetch_image_urls_with_gpt(scene_descriptions)
    paths = download_scene_images(urls, scene_descriptions)
    return paths
