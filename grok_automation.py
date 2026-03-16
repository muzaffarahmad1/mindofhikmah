#!/usr/bin/env python3
"""
MindOfHikmah — Grok Video Automation
Uses Playwright to automate Grok video generation for each scene.
Logs into grok.com, generates each clip, downloads to output folder.
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
GROK_URL = "https://grok.com"
VIDEO_URL = "https://grok.com"


def load_creds():
    with open(CREDS_FILE) as f:
        return json.load(f)


async def login(page, email, password):
    """Log into Grok using email/password via Google."""
    log.info("Logging into Grok...")
    await page.goto(GROK_URL, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    # Check if already logged in
    if await page.query_selector('[data-testid="user-menu"]') or \
       await page.query_selector('textarea'):
        log.info("Already logged in")
        return True

    # Click Sign In
    sign_in = await page.query_selector('a[href*="signin"], button:has-text("Sign in"), a:has-text("Sign in")')
    if sign_in:
        await sign_in.click()
        await page.wait_for_timeout(2000)

    # Try Google login button
    google_btn = await page.query_selector('button:has-text("Google"), a:has-text("Google"), [data-provider="google"]')
    if google_btn:
        await google_btn.click()
        await page.wait_for_timeout(3000)

        # Google login flow
        email_input = await page.wait_for_selector('input[type="email"]', timeout=10000)
        await email_input.fill(email)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        password_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
        await password_input.fill(password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(5000)

        # Handle 2FA or verification if needed
        await page.wait_for_timeout(3000)
        log.info("Google login completed")
        return True

    # Fallback: direct email/password
    email_input = await page.query_selector('input[type="email"], input[name="email"]')
    if email_input:
        await email_input.fill(email)
        pwd_input = await page.query_selector('input[type="password"]')
        if pwd_input:
            await pwd_input.fill(password)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(5000)
        return True

    log.error("Could not find login button")
    return False


async def save_session(context):
    """Save browser session cookies for reuse."""
    cookies = await context.cookies()
    with open(SESSION_FILE, "w") as f:
        json.dump(cookies, f)
    log.info("Session saved")


async def load_session(context):
    """Load saved session cookies."""
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


async def generate_video_clip(page, prompt, output_path, scene_num, max_retries=3):
    """Generate one video clip in Grok and download it."""
    log.info(f"  Scene {scene_num}: Generating video clip...")

    for attempt in range(max_retries):
        try:
            # Navigate to Grok
            await page.goto(GROK_URL, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # Find the input/prompt area
            textarea = await page.wait_for_selector(
                'textarea, div[contenteditable="true"], input[type="text"]',
                timeout=15000
            )

            # Clear and type the video prompt
            await textarea.click()
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(500)

            # Type the video generation prompt
            video_prompt = f"/video {prompt}"
            await textarea.type(video_prompt, delay=20)
            await page.wait_for_timeout(1000)
            await page.keyboard.press("Enter")

            log.info(f"  Scene {scene_num}: Prompt submitted, waiting for generation...")

            # Wait for video to generate (can take 1-3 minutes)
            video_element = await page.wait_for_selector(
                'video, [data-testid="video-result"], .video-result',
                timeout=300000  # 5 min timeout
            )

            if not video_element:
                log.warning(f"  Scene {scene_num}: No video element found, retrying...")
                continue

            await page.wait_for_timeout(3000)

            # Try to find download button
            download_btn = await page.query_selector(
                'button[aria-label*="download"], button:has-text("Download"), a[download]'
            )

            if download_btn:
                # Set up download handler
                async with page.expect_download(timeout=60000) as download_info:
                    await download_btn.click()
                download = await download_info.value
                await download.save_as(str(output_path))
                log.info(f"  Scene {scene_num}: Downloaded via button to {output_path}")
                return True

            # Fallback: get video src and download directly
            video_src = await page.eval_on_selector(
                'video',
                'el => el.src || el.querySelector("source")?.src'
            )

            if video_src and video_src.startswith("http"):
                import urllib.request
                urllib.request.urlretrieve(video_src, str(output_path))
                log.info(f"  Scene {scene_num}: Downloaded via URL to {output_path}")
                return True

            log.warning(f"  Scene {scene_num}: Could not download, attempt {attempt+1}/{max_retries}")
            await page.wait_for_timeout(5000)

        except Exception as e:
            log.error(f"  Scene {scene_num}: Error on attempt {attempt+1}: {e}")
            await page.wait_for_timeout(5000)

    log.error(f"  Scene {scene_num}: All attempts failed")
    return False


async def run_grok_automation(script_path: Path, output_dir: Path):
    """Main automation: generate all video clips for an episode."""
    from playwright.async_api import async_playwright

    # Load script
    with open(script_path) as f:
        script = json.load(f)

    scenes = script.get("scenes", [])
    scientist = script.get("scientist_name", "Scholar")
    log.info(f"Generating {len(scenes)} clips for: {scientist}")

    clips_dir = output_dir / "grok_clips"
    clips_dir.mkdir(exist_ok=True)

    creds = load_creds()
    email = creds["grok_email"]
    password = creds["grok_password"]

    async with async_playwright() as p:
        # Launch browser (headless for server)
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1920,1080"
            ]
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        page = await context.new_page()

        # Try loading saved session first
        session_loaded = await load_session(context)

        # Verify session is still valid
        if session_loaded:
            await page.goto(GROK_URL, wait_until="networkidle")
            await page.wait_for_timeout(2000)
            is_logged_in = await page.query_selector('textarea, [data-testid="user-menu"]')
            if not is_logged_in:
                log.info("Session expired, logging in again...")
                session_loaded = False

        if not session_loaded:
            success = await login(page, email, password)
            if not success:
                log.error("Login failed — check credentials")
                await browser.close()
                return []
            await save_session(context)

        # Generate each scene
        results = []
        for scene in scenes:
            n = scene["number"]
            scene_type = scene.get("type", "narrative")

            # Skip title and end cards — use fallback images for those
            if scene_type in ("title", "end"):
                log.info(f"  Scene {n}: Skipping {scene_type} card (will use styled frame)")
                results.append({"scene": n, "status": "skipped", "type": scene_type})
                continue

            clip_path = clips_dir / f"scene_{n:03d}.mp4"

            # Skip if already generated
            if clip_path.exists() and clip_path.stat().st_size > 50000:
                log.info(f"  Scene {n}: Already exists, skipping")
                results.append({"scene": n, "status": "cached", "path": str(clip_path)})
                continue

            # Build the Grok video prompt
            grok_prompt = build_grok_prompt(scene, script)

            success = await generate_video_clip(page, grok_prompt, clip_path, n)

            if success:
                results.append({"scene": n, "status": "generated", "path": str(clip_path)})
            else:
                results.append({"scene": n, "status": "failed"})

            # Rate limiting — wait between generations
            log.info(f"  Scene {n}: Waiting 15s before next clip...")
            await page.wait_for_timeout(15000)

        await browser.close()

    # Save results
    results_file = output_dir / "grok_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)

    generated = [r for r in results if r["status"] == "generated"]
    failed = [r for r in results if r["status"] == "failed"]

    log.info(f"Grok automation complete:")
    log.info(f"  Generated: {len(generated)}")
    log.info(f"  Cached:    {len([r for r in results if r['status'] == 'cached'])}")
    log.info(f"  Skipped:   {len([r for r in results if r['status'] == 'skipped'])}")
    log.info(f"  Failed:    {len(failed)}")

    if failed:
        log.warning(f"Failed scenes: {[r['scene'] for r in failed]}")

    return results


def build_grok_prompt(scene, script):
    """Build a cinematic Grok video prompt from a scene."""
    scientist = script.get("scientist_name", "the scholar")
    character = script.get("character_description", "")
    era = script.get("era", "")

    base_prompt = f"""Generate a {scene.get('duration_seconds', 10)} second cinematic video clip.

VISUAL:
{scene.get('image_prompt', scene.get('visual_description', ''))}

CHARACTER (must be consistent):
{character}
Era: {era}

TECHNICAL:
- Shot on ARRI Alexa 35mm anamorphic lens
- 8K Ultra HD, 24fps
- Heavy film grain
- Color grade: deep teal shadows #0D2137, warm amber highlights #F5C842
- Mood: {scene.get('mood', 'cinematic')}
- Setting: {scene.get('setting', '')}

CRITICAL:
- NO dialogue, NO text in frame, NO modern elements
- NO subtitles or captions
- Character mouth may move naturally but NO words
- Voiceover added externally
- Must feel like Kingdom of Heaven / Ridley Scott period epic"""

    return base_prompt


def run(script_path: str, output_dir: str):
    """Entry point."""
    asyncio.run(run_grok_automation(Path(script_path), Path(output_dir)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 grok_automation.py <script.json> <output_dir>")
        print("Example: python3 grok_automation.py output/MOH_xxx/script.json output/MOH_xxx/")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
