import asyncio
import os
import re
import json
import urllib.parse
import requests
from PIL import Image, ImageStat, ImageEnhance
from playwright.async_api import async_playwright

BASE_QUERY = "catgirls"
MAX_IMAGES = 1000
OUTPUT_DIR = "pinterest_images"
JSON_FILE = "metadata.json"
PINTEREST_SESS_COOKIE = ""

QUERY_MODIFIERS = [
    "", "anime", "aesthetic", "art", "cute", "digital art", 
    "wallpaper", "icons", "illustration", "fanart", "outfit", 
    "chibi", "drawing", "pfp", "neko", "manga", "sketches"
]

AI_KEYWORDS = [
    "ai", "midjourney", "stable-diffusion", "stablediffusion", 
    "novelai", "dall-e", "dalle", "bingai", "prompt", "generated", 
    "synth", "sdxl", "sd15", "waifu-diffusion"
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)

def is_ai_url_or_text(text):
    """Method 1: Returns True if text contains AI signatures."""
    text_lower = text.lower()
    return any(re.search(rf'\b{re.escape(kw)}\b', text_lower) for kw in AI_KEYWORDS)

def is_likely_ai_image(image_path):
    """Method 2: Uses Pillow to detect hyper-rendered/over-saturated AI image characteristics."""
    try:
        with Image.open(image_path) as img:
            img = img.convert('RGB')
            
            stat = ImageStat.Stat(img)
            avg_std_dev = sum(stat.stddev) / 3.0
            
            hsv_img = img.convert('HSV')
            stat_hsv = ImageStat.Stat(hsv_img)
            saturation_std_dev = stat_hsv.stddev[1]
            
            if avg_std_dev > 72.0 and saturation_std_dev > 68.0:
                return True, f"High variance (StdDev: {avg_std_dev:.1f}, Sat: {saturation_std_dev:.1f})"
                
            return False, "Passed"
    except Exception as e:
        return False, f"Analysis skipped ({e})"

def get_dominant_color_and_category(image_path):
    try:
        with Image.open(image_path) as img:
            img = img.convert('RGB')
            img = img.resize((50, 50))
            
            palette_img = img.quantize(colors=5)
            palette = palette_img.getpalette()
            color_counts = palette_img.getcolors()
            
            dominant_color_index = max(color_counts, key=lambda x: x[0])[1]
            r = palette[dominant_color_index * 3]
            g = palette[dominant_color_index * 3 + 1]
            b = palette[dominant_color_index * 3 + 2]
            
            hex_code = f"#{r:02x}{g:02x}{b:02x}"
            category = categorize_color(r, g, b)
            
            return {"rgb": [r, g, b], "hex": hex_code, "category": category}
    except Exception as e:
        print(f"[ERROR] Color processing failed for {image_path}: {e}")
        return {"rgb": [0, 0, 0], "hex": "#000000", "category": "other"}

def categorize_color(r, g, b):
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    if max_c < 40:
        return "black"
    if min_c > 220:
        return "white"
    if diff < 25:
        return "gray"

    if max_c == r:
        hue = (60 * ((g - b) / diff) + 360) % 360 if diff != 0 else 0
    elif max_c == g:
        hue = (60 * ((b - r) / diff) + 120) % 360
    else:
        hue = (60 * ((r - g) / diff) + 240) % 360

    if 330 <= hue or hue < 15:
        return "red"
    elif 15 <= hue < 45:
        return "orange"
    elif 45 <= hue < 70:
        return "yellow"
    elif 70 <= hue < 165:
        return "green"
    elif 165 <= hue < 260:
        return "blue"
    elif 260 <= hue < 290:
        return "purple"
    elif 290 <= hue < 330:
        return "pink"
    
    return "other"

async def scrape_single_query(page, query, image_urls, max_images):
    search_url = f"https://www.pinterest.com/search/pins/?q={urllib.parse.quote(query)}"
    print(f"\n--- Navigating to: '{query}' ---")
    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        print(f"Timeout loading page for query '{query}', continuing...")
        return

    await page.wait_for_timeout(2500)

    scroll_attempts = 0
    last_count = len(image_urls)
    stuck_count = 0

    while len(image_urls) < max_images and scroll_attempts < 40:
        current_count = len(image_urls)
        print(f"Total collected: {current_count}/{max_images} image URLs...")

        if current_count >= max_images:
            break

        if current_count == last_count:
            stuck_count += 1
        else:
            stuck_count = 0
        last_count = current_count

        if stuck_count >= 5:
            print(f"Reached page limit for query '{query}'. Switching to next search variation.")
            break

        await page.mouse.wheel(0, 2000)
        await page.wait_for_timeout(1200)
        scroll_attempts += 1

async def scrape_pinterest(base_query, max_images):
    image_urls = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900}
        )

        if PINTEREST_SESS_COOKIE:
            await context.add_cookies([{
                "name": "_pinterest_sess",
                "value": PINTEREST_SESS_COOKIE,
                "domain": ".pinterest.com",
                "path": "/"
            }])

        page = await context.new_page()
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        async def handle_response(response):
            try:
                url = response.url
                if "i.pinimg.com" in url and not url.endswith(".gif"):
                    if not is_ai_url_or_text(url):
                        high_res = re.sub(r'/\d+x/', '/736x/', url)
                        image_urls.add(high_res)
                elif "resource" in url or "json" in response.headers.get("content-type", ""):
                    text = await response.text()
                    matches = re.findall(r'https://i\.pinimg\.com/[^\s"\'\\]+', text)
                    for match in matches:
                        if not match.endswith(".gif") and not is_ai_url_or_text(match):
                            high_res = re.sub(r'/\d+x/', '/736x/', match)
                            image_urls.add(high_res)
            except Exception:
                pass

        page.on("response", handle_response)

        for modifier in QUERY_MODIFIERS:
            if len(image_urls) >= max_images:
                break
            
            full_query = f"{base_query} {modifier}".strip()
            await scrape_single_query(page, full_query, image_urls, max_images)

        await browser.close()

    return list(image_urls)[:max_images]

def download_and_process_images(urls, query):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    print(f"\nFinished scraping. Found {len(urls)} candidate URLs. Starting download & AI filtering...")
    base_filename = slugify(query)
    metadata = []
    saved_count = 0

    for i, url in enumerate(urls, start=1):
        temp_filename = f"{base_filename}_temp.jpg"
        temp_filepath = os.path.join(OUTPUT_DIR, temp_filename)
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                with open(temp_filepath, "wb") as f:
                    f.write(response.content)
                
                is_ai, reason = is_likely_ai_image(temp_filepath)
                if is_ai:
                    print(f"[{i}/{len(urls)}] [REJECTED AI] {url} | Reason: {reason}")
                    if os.path.exists(temp_filepath):
                        os.remove(temp_filepath)
                    continue

                saved_count += 1
                final_filename = f"{base_filename}_{saved_count}.jpg"
                final_filepath = os.path.join(OUTPUT_DIR, final_filename)
                
                os.rename(temp_filepath, final_filepath)
                
                color_info = get_dominant_color_and_category(final_filepath)
                
                metadata.append({
                    "id": saved_count,
                    "filename": final_filename,
                    "local_path": f"{OUTPUT_DIR}/{final_filename}",
                    "source_url": url,
                    "hex": color_info["hex"],
                    "rgb": color_info["rgb"],
                    "category": color_info["category"]
                })
                print(f"[{saved_count}] [SAVED] {final_filename} | Category: {color_info['category']}")
            else:
                print(f"[FAILED] HTTP {response.status_code} for {url}")
        except Exception as e:
            print(f"[ERROR] Could not process {url}: {e}")

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"\n[METADATA] Saved {len(metadata)} non-AI entries to '{JSON_FILE}'")

if __name__ == "__main__":
    urls = asyncio.run(scrape_pinterest(BASE_QUERY, MAX_IMAGES))
    download_and_process_images(urls, BASE_QUERY)