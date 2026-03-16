#!/usr/bin/env python3
"""
MindOfHikmah — Grok Video Automation v2
Fixed selector: tiptap ProseMirror div
Clip duration: 6 seconds (Grok free tier)
"""
import os, json, sys, time, logging, asyncio
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path.home() / "youtube-auto"
load_dotenv(BASE_DIR / "credentials" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "grok.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

CREDS_FILE = BASE_DIR / "credentials" / "grok_creds.json"
SESSION_FILE = BASE_DIR / "credentials" / "grok_session.json"
CLIP_DURATION = 6  # Grok free tier = 6 second clips


def load_creds():
    with open(CREDS_FILE) as f:
        return json.load(f)


async def save_session(context):
    cookies = await context.cookies()
    with open(SESSION_FILE, "w") as f:
        json.dump(cookies, f)
    log.info("Session saved")


async def load_session(context):
    if not SESSION_FILE.exists():
        return False
    try:
        with open(SESSION_FILE) as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        log.info("Session loaded from cache")
        return True
    except Exception:
        return False


async def login(page, email, password):
    log.info("Logging into Grok...")
    await page.goto("https://grok.com", wait_until="networkidle")
    await page.wait_for_timeout(3000)

    # Check if already logged in — look for ProseMirror editor
    editor = await page.query_selector('.ProseMirror, .tiptap')
    if editor:
        log.info("Already logged in")
        return True

    # Click Sign In
    sign_in = await page.query_selector('a[href*="signin"], button:has-text("Sign in"), a:has-text("Sign in"), button:has-text("Log in")')
    if sign_in:
        await sign_in.click()
        await page.wait_for_timeout(2000)

    # Google login
    google_btn = await page.query_selector('button:has-text("Google"), a:has-text("Google"), [data-provider="google"]')
    if google_btn:
        await google_btn.click()
        await page.wait_for_timeout(3000)
        email_input = await page.wait_for_selector('input[type="email"]', timeout=10000)
        await email_input.fill(email)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)
        password_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
        await password_input.fill(password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(5000)
        log.info("Google login completed")
        return True

    log.error("Could not find login button")
    return False


async def type_into_prosemirror(page, text):
    """Type text into Grok's ProseMirror/tiptap editor."""
    # Click the editor
    editor = await page.wait_for_selector('.tiptap.ProseMirror, .ProseMirror', timeout=15000)
    await editor.click()
    await page.wait_for_timeout(500)

    # Clear existing content
    await page.keyboard.press("Control+a")
    await page.keyboard.press("Delete")
    await page.wait_for_timeout(300)

    # Type the prompt
    await editor.type(text, delay=10)
    await page.wait_for_timeout(500)


async def find_and_click_send(page):
    """Find and click the send/submit button."""
    # Try various send button selectors
    selectors = [
        'button[aria-label*="Send"]',
        'button[aria-label*="send"]',
        'button[type="submit"]',
        'button:has-text("Send")',
        '[data-testid="send-button"]',
        'button.send-button',
        # SVG arrow button
        'button svg[data-icon*="arrow"], button svg[data-icon*="send"]',
    ]
    for sel in selectors:
        btn = await page.query_selector(sel)
        if btn:
            await btn.click()
            log.info(f"  Clicked send button: {sel}")
            return True

    # Fallback: press Enter
    log.info("  Send button not found, pressing Enter")
    await page.keyboard.press("Enter")
    return True


async def wait_for_video(page, timeout_ms=300000):
    """Wait for Grok to finish generating the video."""
    log.info("  Waiting for video generation...")

    # First wait for any loading indicator to appear
    await page.wait_for_timeout(3000)

    # Wait for video element or download button
    try:
        # Try video element first
        video = await page.wait_for_selector(
            'video, video source, [data-testid*="video"]',
            timeout=timeout_ms
        )
        if video:
            await page.wait_for_timeout(2000)
            return "video"
    except Exception:
        pass

    # Try download button
    try:
        download_btn = await page.wait_for_selector(
            'button[aria-label*="Download"], button[aria-label*="download"], a[download]',
            timeout=30000
        )
        if download_btn:
            return "download_button"
    except Exception:
        pass

    return None


async def download_video(page, output_path):
    """Download the generated video."""
    # Method 1: Download button
    download_btn = await page.query_selector(
        'button[aria-label*="Download"], button[aria-label*="download"], a[download], button:has-text("Download")'
    )
    if download_btn:
        try:
            async with page.expect_download(timeout=60000) as download_info:
                await download_btn.click()
            download = await download_info.value
            await download.save_as(str(output_path))
            log.info(f"  Downloaded via button: {output_path.name}")
            return True
        except Exception as e:
            log.warning(f"  Button download failed: {e}")

    # Method 2: Get video src directly
    try:
        video_src = await page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return v.src || (v.querySelector('source') ? v.querySelector('source').src : null);
        }""")
        if video_src and video_src.startswith("http") and not video_src.startswith("blob"):
            import urllib.request
            urllib.request.urlretrieve(video_src, str(output_path))
            log.info(f"  Downloaded via URL: {output_path.name}")
            return True
    except Exception as e:
        log.warning(f"  URL download failed: {e}")

    # Method 3: Intercept blob URL
    try:
        video_data = await page.evaluate("""async () => {
            const v = document.querySelector('video');
            if (!v || !v.src) return null;
            if (v.src.startsWith('blob:')) {
                const resp = await fetch(v.src);
                const buf = await resp.arrayBuffer();
                return Array.from(new Uint8Array(buf));
            }
            return null;
        }""")
        if video_data:
            output_path.write_bytes(bytes(video_data))
            log.info(f"  Downloaded via blob: {output_path.name}")
            return True
    except Exception as e:
        log.warning(f"  Blob download failed: {e}")

    return False


def build_grok_prompt(scene, script):
    """Build a 6-second Grok video prompt."""
    scientist = script.get("scientist_name", "the scholar")
    character = script.get("character_description", "")
    era = script.get("era", "")

    prompt = f"""Generate a 6 second cinematic video clip. No dialogue. No text in frame.

VISUAL: {scene.get('image_prompt', '')}

SETTING: {scene.get('setting', '')}
MOOD: {scene.get('mood', 'dramatic')}
ERA: {era}

CHARACTER: {character}

STYLE: ARRI Alexa 35mm anamorphic. Heavy film grain. Deep teal shadows, warm amber highlights. Kingdom of Heaven / Ridley Scott epic. Photorealistic. 24fps.

CRITICAL: Silent scene. No words, no subtitles, no modern elements. Voiceover added separately."""

    return prompt


async def generate_one_clip(page, scene, script, output_path, max_retries=3):
    """Generate a single video clip."""
    for attempt in range(max_retries):
        try:
            log.info(f"  Attempt {attempt+1}/{max_retries}")

            # Navigate fresh for each clip
            await page.goto("https://grok.com", wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # Build prompt
            prompt = build_grok_prompt(scene, script)

            # Type into editor
            await type_into_prosemirror(page, prompt)
            await page.wait_for_timeout(1000)

            # Take screenshot to debug
            await page.screenshot(path=f'/tmp/grok_before_send_{scene["number"]}.png')

            # Send
            await find_and_click_send(page)

            # Wait for video
            result = await wait_for_video(page, timeout_ms=300000)

            if not result:
                log.warning(f"  No video found on attempt {attempt+1}")
                await page.screenshot(path=f'/tmp/grok_after_wait_{scene["number"]}.png')
                continue

            # Download
            success = await download_video(page, output_path)
            if success:
                size = output_path.stat().st_size if output_path.exists() else 0
                if size > 10000:
                    log.info(f"  Clip saved: {size//1024}KB")
                    return True
                else:
                    log.warning(f"  File too small: {size} bytes")

        except Exception as e:
            log.error(f"  Attempt {attempt+1} error: {e}")
            await page.screenshot(path=f'/tmp/grok_error_{scene["number"]}_{attempt}.png')
            await page.wait_for_timeout(5000)

    return False


async def run_grok_automation(script_path: Path, output_dir: Path):
    """Main automation function."""
    from playwright.async_api import async_playwright

    with open(script_path) as f:
        script = json.load(f)

    scenes = script.get("scenes", [])
    scientist = script.get("scientist_name", "Scholar")
    log.info(f"Generating clips for: {scientist} ({len(scenes)} scenes)")

    clips_dir = output_dir / "grok_clips"
    clips_dir.mkdir(exist_ok=True)

    creds = load_creds()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

        # Load or create session
        session_loaded = await load_session(context)
        page = await context.new_page()

        if session_loaded:
            await page.goto("https://grok.com", wait_until="networkidle")
            await page.wait_for_timeout(2000)
            editor = await page.query_selector('.ProseMirror, .tiptap')
            if not editor:
                log.info("Session expired, logging in again...")
                session_loaded = False

        if not session_loaded:
            success = await login(page, creds["grok_email"], creds["grok_password"])
            if not success:
                log.error("Login failed")
                await browser.close()
                return []
            await save_session(context)

        results = []
        for scene in scenes:
            n = scene["number"]
            scene_type = scene.get("type", "narrative")

            if scene_type in ("title", "end"):
                log.info(f"Scene {n}: Skipping {scene_type} card")
                results.append({"scene": n, "status": "skipped"})
                continue

            clip_path = clips_dir / f"scene_{n:03d}.mp4"

            if clip_path.exists() and clip_path.stat().st_size > 50000:
                log.info(f"Scene {n}: Already exists ({clip_path.stat().st_size//1024}KB)")
                results.append({"scene": n, "status": "cached", "path": str(clip_path)})
                continue

            log.info(f"Scene {n}: {scene.get('name', '')} — {scene.get('mood', '')}")
            success = await generate_one_clip(page, scene, script, clip_path)

            if success:
                results.append({"scene": n, "status": "generated", "path": str(clip_path)})
                log.info(f"Scene {n}: SUCCESS")
            else:
                results.append({"scene": n, "status": "failed"})
                log.warning(f"Scene {n}: FAILED — will use fallback image")

            # Wait between clips to avoid rate limiting
            if n < len(scenes):
                log.info("Waiting 20s before next clip...")
                await page.wait_for_timeout(20000)

        await browser.close()

    # Summary
    generated = sum(1 for r in results if r["status"] == "generated")
    cached = sum(1 for r in results if r["status"] == "cached")
    failed = sum(1 for r in results if r["status"] == "failed")
    log.info(f"Complete: {generated} generated, {cached} cached, {failed} failed")

    with open(output_dir / "grok_results.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 grok_automation.py <script.json> <output_dir>")
        sys.exit(1)
    asyncio.run(run_grok_automation(Path(sys.argv[1]), Path(sys.argv[2])))
