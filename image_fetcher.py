# image_fetcher.py - GPT-4o يجيب روابط صور قابلة للتحميل مع Pollinations كـ fallback

import json
import re
import os
import time
import urllib.parse
import requests
from config import GITHUB_TOKEN, IMAGES_DIR

GITHUB_MODELS_URL = "https://models.github.ai/inference/chat/completions"

DL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}


def _verify_url(url: str) -> bool:
    try:
        r = requests.head(url, headers=DL_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code == 200 and "image" in r.headers.get("Content-Type", ""):
            return True
        if r.status_code in (403, 405):
            r2 = requests.get(url, headers=DL_HEADERS, timeout=15, stream=True)
            if r2.status_code == 200 and "image" in r2.headers.get("Content-Type", ""):
                r2.close()
                return True
    except Exception:
        pass
    return False


def _ask_gpt_for_urls(scene_descriptions: list, exclude_urls: list = None) -> list:
    exclude_note = ""
    if exclude_urls:
        exclude_note = f"\n\nDo NOT use any of these URLs (they failed):\n" + "\n".join(exclude_urls)

    scenes_text = "\n\n".join(
        f"[Scene {i+1}]: {desc}" for i, desc in enumerate(scene_descriptions)
    )

    prompt = f"""You are a visual researcher finding real downloadable images for a YouTube video.

For each scene description below, find ONE image URL that:
- DIRECTLY and VISUALLY matches the scene content — if the scene is about hibernation, find a photo of hibernating animals or a scientist in a lab, NOT an aerial view of houses
- Is a DIRECT link to an image file (.jpg, .jpeg, .png, .webp) that returns HTTP 200
- Is publicly accessible without login or paywall
- Is at least 800x600 resolution

CRITICAL MATCHING RULES:
- Read each scene description carefully and find an image of EXACTLY what is described
- If the scene mentions a specific animal, person, place, or event — find that exact thing
- Do NOT pick generic or loosely related images
- Do NOT pick images just because they share one word with the description

ALLOWED sources (direct image links only):
- NASA: nasa.gov direct image files
- ESA: esa.int direct image files  
- Unsplash: images.unsplash.com/photo-... 
- Pexels: images.pexels.com/photos/...
- Wikimedia Commons DIRECT file links: upload.wikimedia.org/wikipedia/commons/...
- Any .gov or .edu site with direct image files{exclude_note}

Scenes:
{scenes_text}

Reply with JSON ONLY:
{{"images": [
  {{"scene": 1, "url": "https://...", "source": "Unsplash"}},
  ...
]}}

Exactly {len(scene_descriptions)} items."""

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4000,
        "temperature": 0.2,
    }

    for attempt in range(3):
        try:
            response = requests.post(GITHUB_MODELS_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            raw = re.sub(r"```json|```", "", raw).strip()
            data = json.loads(raw)
            images = data.get("images", [])
            if len(images) == len(scene_descriptions):
                return images
            print(f"⚠️ محاولة {attempt+1}: رجع {len(images)} بدل {len(scene_descriptions)} — retry")
        except Exception as e:
            print(f"⚠️ محاولة {attempt+1} فشلت: {e} — retry")

    return []


def _pollinations_fallback(description: str, img_path: str) -> bool:
    encoded = urllib.parse.quote(description[:200])
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1280&height=720&nologo=true&model=flux"
    for attempt in range(3):
        try:
            print(f"  🎨 Pollinations fallback (محاولة {attempt+1})...")
            r = requests.get(url, timeout=60, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 3000:
                with open(img_path, "wb") as f:
                    f.write(r.content)
                print(f"  ✅ Pollinations: جاهزة")
                return True
            time.sleep(3)
        except Exception as e:
            print(f"  ⚠️ Pollinations خطأ: {e}")
            time.sleep(3)
    return False


def download_scene_images(urls_data: list, scene_descriptions: list) -> list:
    os.makedirs(IMAGES_DIR, exist_ok=True)
    paths = []

    for i, (img_data, desc) in enumerate(zip(urls_data, scene_descriptions)):
        url = img_data.get("url", "")
        source = img_data.get("source", "?")
        safe = "".join(c if c.isalnum() else "_" for c in desc[:30])
        img_path = os.path.join(IMAGES_DIR, f"scene_{i+1}_{safe}.jpg")

        if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
            print(f"  ✅ مشهد {i+1}: موجودة")
            paths.append(img_path)
            continue

        downloaded = False

        if not url or not url.startswith("http"):
            print(f"  ⚠️ مشهد {i+1}: URL فاضي — Pollinations")
        else:
            print(f"  ⬇️ مشهد {i+1} [{source}]: بيتحمل...")
            try:
                r = requests.get(url, headers=DL_HEADERS, timeout=30, allow_redirects=True)
                if r.status_code == 200 and len(r.content) > 3000 and "image" in r.headers.get("Content-Type", ""):
                    with open(img_path, "wb") as f:
                        f.write(r.content)
                    print(f"  ✅ مشهد {i+1}: جاهزة")
                    paths.append(img_path)
                    downloaded = True
                else:
                    print(f"  ❌ مشهد {i+1}: فشل (status {r.status_code})")
            except Exception as e:
                print(f"  ❌ مشهد {i+1}: خطأ — {e}")

        if not downloaded:
            success = _pollinations_fallback(desc, img_path)
            paths.append(img_path if success else None)

    return paths


def fetch_image_urls_with_gpt(scene_descriptions: list) -> list:
    print(f"🔍 GPT-4o بيدور على {len(scene_descriptions)} صورة...")
    images = _ask_gpt_for_urls(scene_descriptions)

    if not images:
        print("⚠️ GPT-4o فشل — Pollinations للكل")
        return [{"scene": i+1, "url": "", "source": "pollinations"} for i in range(len(scene_descriptions))]

    print("🔎 بيتحقق من الـ URLs...")
    failed = []
    for img in images:
        url = img.get("url", "")
        if url and _verify_url(url):
            print(f"  ✅ مشهد {img['scene']}: {img['source']} — OK")
        else:
            print(f"  ❌ مشهد {img['scene']}: فشل التحقق")
            failed.append(img)
            img["url"] = ""

    if failed:
        print(f"⚠️ {len(failed)} فشلوا — بيطلب بدائل...")
        failed_scenes = [scene_descriptions[f["scene"]-1] for f in failed]
        failed_urls = [f.get("url", "") for f in failed if f.get("url")]
        replacements = _ask_gpt_for_urls(failed_scenes, exclude_urls=failed_urls)
        if replacements:
            for orig, rep in zip(failed, replacements):
                if _verify_url(rep.get("url", "")):
                    orig["url"] = rep["url"]
                    orig["source"] = rep["source"]
                    print(f"  ✅ مشهد {orig['scene']}: بديل OK")

    return images


def get_scene_images(scene_descriptions: list) -> list:
    urls_data = fetch_image_urls_with_gpt(scene_descriptions)
    return download_scene_images(urls_data, scene_descriptions)
