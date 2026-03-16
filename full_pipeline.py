#!/usr/bin/env python3
"""
MindOfHikmah — Full Automated Pipeline
Idea -> Script -> Images -> Voice -> Video -> Thumbnail -> YouTube -> Notify
Voice: en-GB-RyanNeural (edge-tts, free)
Music: Arabian Nights (royalty-free, auto-downloaded)
Images: Pollinations.ai (free, no API key)
"""
import os, sys, json, asyncio, logging, datetime, subprocess, time, urllib.request, urllib.parse
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path.home() / "youtube-auto"
load_dotenv(BASE_DIR / "credentials" / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "pipeline.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

import anthropic
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

VOICE = "en-GB-RyanNeural"
MUSIC_URLS = [
    "https://archive.org/download/incompetech-collection-0/Arabiannights.mp3",
    "https://archive.org/download/Kevin_MacLeod_Incompetech/Arabian%20Nights.mp3",
    "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Arabian%20Nights.mp3",
]

CHANNEL_BRIEF = """
CHANNEL: MindOfHikmah
MISSION: Tell the stories of Muslim scientists and scholars whose contributions
changed the world but history largely forgot.
TONE: Like a brilliant friend sharing the most incredible thing they discovered.
Wonder and quiet outrage. Never academic. Short punchy sentences. Silence has power.
STORYTELLING: Story drives length. Hook within 3 seconds. End with emotional punch.
Facts 100% accurate. Drama comes from the truth.
VISUAL: Dark cinematic. Deep teal shadows. Warm amber highlights. Kingdom of Heaven style.
""".strip()


# ── STEP 1: GENERATE SCRIPT ─────────────────────────────────────────────────

def generate_script(idea):
    log.info("Step 1/7: Generating script...")
    response = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=5000,
        system=[
            {"type": "text", "text": CHANNEL_BRIEF, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": "Return ONLY valid JSON. No markdown. No backticks. No explanation."}
        ],
        messages=[{"role": "user", "content": f"""
Write a complete MindOfHikmah YouTube video script about: {idea}

Let the story breathe naturally. No fixed scene count. Each scene = one visual moment 8-15 seconds.
Max 25 words of voiceover per scene. Short punchy sentences. Pauses are powerful.

Return this exact JSON structure:
{{
  "title": "YouTube title max 60 chars with curiosity hook",
  "scientist_name": "Full historical name",
  "era": "Time and place e.g. 10th Century Baghdad",
  "hook": "One sentence that stops someone scrolling",
  "character_description": "Age, clothing, physical features, historically accurate, for image generation",
  "scenes": [
    {{
      "number": 1,
      "name": "short scene name",
      "type": "title",
      "setting": "where and when",
      "mood": "mysterious",
      "voiceover": "narration text max 25 words",
      "image_prompt": "detailed cinematic scene description for AI image generation, no text in image, period accurate",
      "duration_seconds": 8,
      "is_short_candidate": false
    }}
  ],
  "description": "Full YouTube description 300 words with timestamps and hashtags",
  "tags": ["tag1", "tag2", "tag3"],
  "pinned_comment": "Engaging question to pin as first comment"
}}

Scene types: title, narrative, action, reveal, legacy, end
Include a title scene first and end scene last.
"""}]
    )
    raw = response.content[0].text.strip()
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip().rstrip("`").strip()
    script = json.loads(raw)
    log.info(f"  Script: {script['title']} ({len(script['scenes'])} scenes)")
    return script


# ── STEP 2: GENERATE IMAGES ──────────────────────────────────────────────────

def generate_image(prompt, output_path, width=1920, height=1080):
    enhanced = (
        f"cinematic film still, {prompt}, "
        "dark atmospheric lighting, deep teal shadows, warm amber highlights, "
        "8K resolution, anamorphic lens, heavy film grain, "
        "Kingdom of Heaven style period epic, photorealistic, "
        "no text, no watermark, no modern elements"
    )
    encoded = urllib.parse.quote(enhanced)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true&model=flux"
    try:
        log.info(f"  Generating: {output_path.name}")
        req = urllib.request.Request(url, headers={"User-Agent": "MindOfHikmah/1.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
        if len(data) < 5000:
            log.warning(f"  Image too small ({len(data)} bytes)")
            return False
        output_path.write_bytes(data)
        log.info(f"  Saved {len(data)//1024}KB")
        return True
    except Exception as e:
        log.error(f"  Image failed: {e}")
        return False


def create_fallback_image(scene, output_path, scientist):
    from PIL import Image, ImageDraw, ImageFont
    import math
    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), (13, 33, 55))
    draw = ImageDraw.Draw(img)
    for gx in range(-180, W + 180, 180):
        for gy in range(-180, H + 180, 180):
            for i in range(8):
                a = (i * 45) * math.pi / 180
                x1 = gx + 40 * math.cos(a)
                y1 = gy + 40 * math.sin(a)
                x2 = gx + 70 * math.cos(a + math.pi / 8)
                y2 = gy + 70 * math.sin(a + math.pi / 8)
                draw.line([(x1, y1), (x2, y2)], fill=(212, 168, 83, 25), width=1)
    try:
        fl = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf", 72)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", 32)
    except Exception:
        fl = fs = ImageFont.load_default()
    draw.text((W // 2, H // 2 - 60), scientist, font=fl, fill=(248, 246, 240), anchor="mm")
    draw.text((W // 2, H // 2 + 40), scene.get("setting", ""), font=fs, fill=(212, 168, 83), anchor="mm")
    draw.text((W // 2, H - 80), "MindOfHikmah", font=fs, fill=(120, 100, 80), anchor="mm")
    img.save(output_path, "JPEG", quality=95)


def generate_all_images(script, output_dir):
    log.info("Step 2/7: Generating scene images...")
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    scientist = script.get("scientist_name", "The Scholar")
    for scene in script["scenes"]:
        n = scene["number"]
        img_path = images_dir / f"scene_{n:03d}.jpg"
        if scene["type"] in ("title", "end"):
            create_fallback_image(scene, img_path, scientist)
        else:
            ok = generate_image(scene["image_prompt"], img_path)
            if not ok:
                log.warning(f"  Fallback image for scene {n}")
                create_fallback_image(scene, img_path, scientist)
        time.sleep(2)
    log.info(f"  {len(script['scenes'])} images ready")
    return images_dir


# ── STEP 3: VOICEOVER ────────────────────────────────────────────────────────

async def tts_scene(text, output_file):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE)
    await communicate.save(str(output_file))


def generate_voiceovers(script, output_dir):
    log.info("Step 3/7: Generating voiceovers...")
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(exist_ok=True)
    for scene in script["scenes"]:
        n = scene["number"]
        vo = scene.get("voiceover", "").strip()
        out = audio_dir / f"scene_{n:03d}.mp3"
        dur = scene.get("duration_seconds", 8)
        if not vo or scene["type"] in ("title", "end"):
            os.system(
                f"ffmpeg -f lavfi -i anullsrc=r=24000:cl=mono "
                f"-t {dur} -q:a 9 -acodec libmp3lame {out} -y -loglevel quiet"
            )
        else:
            log.info(f"  Scene {n}: {vo[:50]}...")
            asyncio.run(tts_scene(vo, out))
            time.sleep(0.5)
    log.info("  Voiceovers complete")
    return audio_dir


# ── STEP 4: BACKGROUND MUSIC ─────────────────────────────────────────────────

def get_background_music():
    music_file = BASE_DIR / "assets" / "music_arabian.mp3"
    if music_file.exists() and music_file.stat().st_size > 100000:
        log.info("Step 4/7: Using cached music")
        return music_file
    log.info("Step 4/7: Downloading background music...")
    for url in MUSIC_URLS:
        try:
            log.info(f"  Trying: {url[:60]}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) > 100000:
                music_file.write_bytes(data)
                log.info(f"  Music downloaded: {len(data) // 1024}KB")
                return music_file
        except Exception as e:
            log.warning(f"  Failed: {e}")
    log.warning("  All music downloads failed — using silence")
    os.system(
        f"ffmpeg -f lavfi -i anullsrc=r=44100:cl=stereo "
        f"-t 600 -q:a 9 -acodec libmp3lame {music_file} -y -loglevel quiet"
    )
    return music_file


# ── STEP 5: ASSEMBLE VIDEO ───────────────────────────────────────────────────

def get_audio_duration(audio_file):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_file)],
        capture_output=True, text=True
    )
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception:
        return None


def assemble_video(script, images_dir, audio_dir, music_file, output_dir):
    log.info("Step 5/7: Assembling video...")
    clips_dir = output_dir / "clips"
    clips_dir.mkdir(exist_ok=True)
    clip_files = []

    for scene in script["scenes"]:
        n = scene["number"]
        img = images_dir / f"scene_{n:03d}.jpg"
        vo_audio = audio_dir / f"scene_{n:03d}.mp3"
        clip_out = clips_dir / f"clip_{n:03d}.mp4"

        if not img.exists():
            log.warning(f"  Missing image scene {n}, skipping")
            continue

        duration = float(scene.get("duration_seconds", 8))
        if vo_audio.exists():
            vo_dur = get_audio_duration(vo_audio)
            if vo_dur:
                duration = max(duration, vo_dur + 2.0)

        frames = int(duration * 25)
        zoom_filter = (
            f"zoompan=z='min(zoom+0.0006,1.25)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s=1920x1080:fps=25"
        )

        if vo_audio.exists():
            cmd = [
                "ffmpeg", "-y", "-loglevel", "warning",
                "-loop", "1", "-i", str(img),
                "-i", str(vo_audio),
                "-vf", zoom_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-t", str(duration), "-pix_fmt", "yuv420p",
                "-shortest", str(clip_out)
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-loglevel", "warning",
                "-loop", "1", "-i", str(img),
                "-vf", zoom_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-t", str(duration), "-pix_fmt", "yuv420p",
                str(clip_out)
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            log.error(f"  Clip {n} failed: {result.stderr[-200:]}")
            continue

        clip_files.append(clip_out)
        log.info(f"  Clip {n} done ({duration:.1f}s)")

    if not clip_files:
        raise RuntimeError("No clips were created")

    concat_file = output_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for clip in clip_files:
            f.write(f"file '{clip}'\n")

    raw_video = output_dir / "raw_video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "warning",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(raw_video)
    ], check=True)

    final_video = output_dir / "final_video.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "warning",
        "-i", str(raw_video),
        "-stream_loop", "-1", "-i", str(music_file),
        "-filter_complex",
        "[1:a]volume=0.07,afade=t=in:st=0:d=3[music];"
        "[0:a][music]amix=inputs=2:duration=first:dropout_transition=3[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(final_video)
    ], check=True)

    size_mb = final_video.stat().st_size / (1024 * 1024)
    log.info(f"  Final video: {size_mb:.1f}MB")
    return final_video


# ── STEP 6: THUMBNAIL ────────────────────────────────────────────────────────

def generate_thumbnail(script, output_dir):
    log.info("Step 6/7: Generating thumbnail...")
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1280, 720
    thumb_path = output_dir / "thumbnail.jpg"
    scientist = script.get("scientist_name", "")
    era = script.get("era", "")

    bg_prompt = (
        f"dramatic cinematic portrait of {scientist} {era} scholar, "
        "emotional expression of wonder and determination, "
        "dark prison cell or study room, shaft of light from small window, "
        "deep teal and amber color grade, Kingdom of Heaven style, "
        "highly detailed photorealistic, no text, no watermark"
    )
    bg_path = output_dir / "thumb_bg.jpg"
    ok = generate_image(bg_prompt, bg_path, W, H)

    if ok:
        img = Image.open(bg_path).convert("RGB")
    else:
        img = Image.new("RGB", (W, H), (13, 33, 55))

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(H):
        alpha = int(140 * (y / H))
        odraw.rectangle([(0, y), (W, y + 1)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    def get_font(size, bold=False):
        paths = [
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        ]
        for p in paths:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    draw.text((40, 36), "MIND OF HIKMAH", font=get_font(22), fill=(212, 168, 83))

    title = script.get("title", "")
    words = title.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= 20:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)

    y = H // 2 - len(lines[:3]) * 50
    for line in lines[:3]:
        draw.text((42, y + 3), line.upper(), font=get_font(78, True), fill=(0, 0, 0, 200))
        draw.text((40, y), line.upper(), font=get_font(78, True), fill=(255, 220, 50))
        y += 90

    draw.text((40, H - 52), f"{scientist}  ·  {era}", font=get_font(26), fill=(200, 180, 140))

    img.save(thumb_path, "JPEG", quality=95)
    log.info(f"  Thumbnail saved")
    return thumb_path


# ── STEP 7: UPLOAD TO YOUTUBE ────────────────────────────────────────────────

def upload_to_youtube(video_file, thumb_file, script, video_id):
    log.info("Step 7/7: Uploading to YouTube as unlisted...")
    import pickle
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube"
    ]
    OAUTH = BASE_DIR / "credentials" / "youtube-oauth.json"
    TOKEN = BASE_DIR / "credentials" / "youtube-token.pickle"

    creds = None
    if TOKEN.exists():
        with open(TOKEN, "rb") as f:
            creds = pickle.load(f)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN, "wb") as f:
            pickle.dump(creds, f)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH), SCOPES)
        creds = flow.run_local_server(port=8080, open_browser=False)
        with open(TOKEN, "wb") as f:
            pickle.dump(creds, f)

    yt = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": script.get("title", "MindOfHikmah")[:100],
            "description": script.get("description", "")[:5000],
            "tags": script.get("tags", []),
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False
        }
    }
    media = MediaFileUpload(
        str(video_file), mimetype="video/mp4",
        resumable=True, chunksize=10 * 1024 * 1024
    )
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log.info(f"  Upload: {int(status.progress() * 100)}%")

    yt_id = response["id"]
    url = f"https://www.youtube.com/watch?v={yt_id}"
    log.info(f"  Uploaded: {url}")

    try:
        yt.thumbnails().set(
            videoId=yt_id,
            media_body=MediaFileUpload(str(thumb_file), mimetype="image/jpeg")
        ).execute()
        log.info("  Thumbnail set")
    except Exception as e:
        log.warning(f"  Thumbnail failed: {e}")

    record = {
        "youtube_id": yt_id, "url": url,
        "title": script.get("title", ""), "status": "unlisted",
        "video_id": video_id,
        "created": datetime.datetime.now().isoformat()
    }
    json.dump(record, open(BASE_DIR / "queue" / f"{video_id}.json", "w"), indent=2)
    return record


# ── NOTIFY ───────────────────────────────────────────────────────────────────

def notify(result, script):
    msg = f"""
{'='*50}
MINDOFHIKMAH — VIDEO READY FOR APPROVAL
{'='*50}
Title:     {script.get('title', '')}
Scientist: {script.get('scientist_name', '')}
URL:       {result['url']}

To PUBLISH: python3 scripts/publish.py {result['youtube_id']}
To REJECT:  delete {BASE_DIR}/queue/{result['video_id']}.json
{'='*50}
"""
    print(msg)
    pending = BASE_DIR / "queue" / "pending_approval.json"
    json.dump(result, open(pending, "w"), indent=2)


# ── PUBLISH HELPER ───────────────────────────────────────────────────────────

def publish(youtube_id):
    import pickle
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    TOKEN = BASE_DIR / "credentials" / "youtube-token.pickle"
    with open(TOKEN, "rb") as f:
        creds = pickle.load(f)
    if creds.expired:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds)
    yt.videos().update(
        part="status",
        body={"id": youtube_id, "status": {"privacyStatus": "public"}}
    ).execute()
    url = f"https://www.youtube.com/watch?v={youtube_id}"
    print(f"Published: {url}")
    return url


# ── MAIN ─────────────────────────────────────────────────────────────────────

def run(idea):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_id = f"MOH_{ts}"
    output_dir = BASE_DIR / "output" / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"MindOfHikmah Pipeline Starting")
    log.info(f"Idea: {idea}")
    log.info(f"Output: {output_dir}")

    script = generate_script(idea)
    json.dump(script, open(output_dir / "script.json", "w"), indent=2, ensure_ascii=False)

    images_dir = generate_all_images(script, output_dir)
    audio_dir = generate_voiceovers(script, output_dir)
    music_file = get_background_music()
    final_video = assemble_video(script, images_dir, audio_dir, music_file, output_dir)
    thumb_file = generate_thumbnail(script, output_dir)
    result = upload_to_youtube(final_video, thumb_file, script, video_id)
    notify(result, script)
    return result


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        if len(sys.argv) < 3:
            print("Usage: python3 full_pipeline.py publish YOUTUBE_VIDEO_ID")
            sys.exit(1)
        publish(sys.argv[2])
    elif len(sys.argv) > 1:
        run(" ".join(sys.argv[1:]))
    else:
        print("Usage: python3 full_pipeline.py 'Your idea here'")
        print("       python3 full_pipeline.py publish YOUTUBE_VIDEO_ID")
        print("")
        print("Example:")
        print("  python3 full_pipeline.py 'Ibn Sina — the father of modern medicine'")
