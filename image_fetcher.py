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
    """يتأكد إن الـ URL صورة حقيقية قابلة للتحميل عبر HEAD request."""
    try:
        r = requests.head(url, headers=DL_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            ct = r.headers.get("Content-Type", "")
            if "image" in ct:
                return True
        # بعض السيرفرات مش بتسمح HEAD — نجرب GET بـ stream
        if r.status_code in (403, 405):
            r2 = requests.get(url, headers=DL_HEADERS, timeout=15, stream=True)
            if r2.status_code == 200 and "image" in r2.headers.get("Content-Type", ""):
                r2.close()
                return True
    except Exception:
        pass
    return False


def _ask_gpt_for_urls(scene_descriptions: list, exclude_urls: list = None) -> list:
    """يطلب من GPT-4o روابط صور مع تعليمات صارمة بالمصادر المسموحة."""

    exclude_note = ""
    if exclude_urls:
        exclude_note = f"\n\nDo NOT use any of these URLs (they failed verification):\n" + "\n".join(exclude_urls)

    scenes_text = "\n\n".join(
        f"[Scene {i+1}]: {desc}" for i, desc in enumerate(scene_descriptions)
    )

    prompt = f"""You are an expert at finding publicly downloadable images for YouTube educational videos.

For each scene, find ONE image URL that:
- Is a DIRECT link to an image file (.jpg, .jpeg, .png, .webp) — NOT a webpage
- Can be downloaded without login, paywall, or authentication
- Is publicly accessible (returns HTTP 200 with Content-Type: image/*)
- Is high resolution (at least 800x600)
- Is NOT from: Wikimedia, Wikipedia Commons, AP Images (newsroom.ap.org), Getty, Shutterstock, Adobe Stock, NPR media, Scientific American CDN, or any paywalled source

BEST sources to use:
- NASA: images.nasa.gov direct image links (e.g. https://www.nasa.gov/wp-content/uploads/...)
- ESA: www.esa.int direct image links
- NOAA: direct .jpg/.png from noaa.gov
- Unsplash: images.unsplash.com/photo-... links
- Pexels: images.pexels.com/photos/... links
- Public domain archives: publicdomainpictures.net, picryl.com
- Any government/educational .gov/.edu site with direct image files{exclude_note}

Scenes:
{scenes_text}

Reply with JSON ONLY:
{{"images": [
  {{"scene": 1, "url": "https://...", "source": "NASA"}},
  {{"scene": 2, "url": "https://...", "source": "Unsplash"}},
  ...
]}}

Exactly {len(scene_descriptions)} items. Direct downloadable image URLs only."""

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
    """يولد صورة عبر Pollinations AI كـ fallback."""
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
    """
    يحمل الصور — لو URL فشل يطلب بديل من GPT، لو فشل كمان يعمل Pollinations.
    urls_data: list of {"scene": N, "url": "...", "source": "..."}
    """
    os.makedirs(IMAGES_DIR, exist_ok=True)
    paths = []
    failed_urls = []

    for i, (img_data, desc) in enumerate(zip(urls_data, scene_descriptions)):
        url = img_data.get("url", "")
        source = img_data.get("source", "?")
        safe = "".join(c if c.isalnum() else "_" for c in desc[:30])
        img_path = os.path.join(IMAGES_DIR, f"scene_{i+1}_{safe}.jpg")

        if os.path.exists(img_path) and os.path.getsize(img_path) > 5000:
            print(f"  ✅ مشهد {i+1}: موجودة")
            paths.append(img_path)
            continue

        # تحميل الـ URL اللي جابه GPT
        downloaded = False
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
                failed_urls.append(url)
        except Exception as e:
            print(f"  ❌ مشهد {i+1}: خطأ — {e}")
            failed_urls.append(url)

        if not downloaded:
            # Pollinations fallback مباشرة
            success = _pollinations_fallback(desc, img_path)
            if success:
                paths.append(img_path)
            else:
                print(f"  ⚠️ مشهد {i+1}: مفيش صورة — fallback")
                paths.append(None)

    return paths


def fetch_image_urls_with_gpt(scene_descriptions: list) -> list:
    """يطلب URLs من GPT-4o ويتحقق منها قبل الاستخدام."""
    print(f"🔍 GPT-4o بيدور على {len(scene_descriptions)} صورة...")
    images = _ask_gpt_for_urls(scene_descriptions)

    if not images:
        print("⚠️ GPT-4o فشل — هيستخدم Pollinations للكل")
        return [{"scene": i+1, "url": "", "source": "pollinations"} for i in range(len(scene_descriptions))]

    # verify كل URL
    print("🔎 بيتحقق من الـ URLs...")
    failed = []
    for img in images:
        url = img.get("url", "")
        if url and _verify_url(url):
            print(f"  ✅ مشهد {img['scene']}: {img['source']} — OK")
        else:
            print(f"  ❌ مشهد {img['scene']}: {url[:60]} — فشل التحقق")
            failed.append(img)
            img["url"] = ""  # هيتعامل معاه كـ fallback في download

    if failed:
        print(f"⚠️ {len(failed)} URL فشلوا — بيطلب بدائل من GPT...")
        failed_scenes = [scene_descriptions[f["scene"]-1] for f in failed]
        failed_urls_list = [f.get("url", "") for f in failed if f.get("url")]
        replacements = _ask_gpt_for_urls(failed_scenes, exclude_urls=failed_urls_list)
        if replacements:
            for orig, rep in zip(failed, replacements):
                if _verify_url(rep.get("url", "")):
                    orig["url"] = rep["url"]
                    orig["source"] = rep["source"]
                    print(f"  ✅ مشهد {orig['scene']}: بديل OK — {rep['source']}")
                else:
                    print(f"  ❌ مشهد {orig['scene']}: البديل كمان فشل — Pollinations")

    return images


def get_scene_images(scene_descriptions: list) -> list:
    """الدالة الرئيسية — تجيب وصف المشاهد وترجع paths للصور المحملة."""
    urls_data = fetch_image_urls_with_gpt(scene_descriptions)
    paths = download_scene_images(urls_data, scene_descriptions)
    return paths
