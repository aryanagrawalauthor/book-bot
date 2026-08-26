"""
Generates a narrated, animated, music-scored reel for one quote.
Runs in GitHub Actions (needs real internet access for the ElevenLabs API call,
which this sandbox doesn't have -- that's why this runs there, not in chat).

Pipeline:
  1. Send quote text to ElevenLabs -> get back an .mp3 narration (deep male voice)
  2. Measure narration duration
  3. Pick a mood-matched background music track based on the quote's theme
  4. Render an animated video (branded background + text lines revealing in sync
     with the narration) using ffmpeg, sized to match narration length
  5. Mix narration (full volume) + music (lowered volume) into the final audio track
  6. Output final .mp4 ready to upload to the repo / add to manifest.json

Required GitHub Actions secret: ELEVENLABS_API_KEY
Required repo files: dramatic_*.mp3 in the repo root (currently only "dramatic"
  mood tracks are set up -- add reflective_*.mp3, calm_*.mp3, uplifting_*.mp3
  later the same way to unlock those moods)

NOTE: Currently only dramatic_*.mp3 tracks exist, so this script filters to
only render quotes whose theme maps to the "dramatic" mood.
"""
import os
import sys
import json
import subprocess
import textwrap
import requests

# ---- CONFIG ----------------------------------------------------------------

ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"   # "Adam" -- deep, clear male voice
ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"

W, H = 1080, 1920   # Reels vertical format
BG = "0x111111"
ACCENT = "0xC4A46A"
TEXT_COLOR = "0xF0EEE8"

SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

OUTPUT_DIR = "reels"

# Maps each quote theme to a music mood prefix (files named <mood>_*.mp3 in repo root)
THEME_TO_MOOD = {
    "Execution": "dramatic", "Action": "dramatic", "Failure": "dramatic",
    "Fear": "dramatic", "Momentum": "dramatic",
    "Awareness": "reflective", "Presence": "reflective",
    "Identity": "reflective", "Self-Belief": "reflective",
    "Emotional Control": "calm", "Planning": "calm",
    "Adaptability": "calm", "Reading the Room": "calm",
    "Confidence": "uplifting", "Growth": "uplifting",
}
DEFAULT_MOOD = "reflective"


# ---- STEP 1: NARRATION -------------------------------------------------

def generate_narration(quote_text, out_path):
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY environment variable is not set.")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    resp = requests.post(
        url,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "text": quote_text,
            "model_id": ELEVENLABS_MODEL_ID,
            "voice_settings": {"stability": 0.55, "similarity_boost": 0.75},
        },
        timeout=60,
    )
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)


def get_audio_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


# ---- STEP 2: PICK MUSIC -------------------------------------------------

def pick_music(theme):
    mood = THEME_TO_MOOD.get(theme, DEFAULT_MOOD)
    prefix = f"{mood}_"
    tracks = [
        f for f in os.listdir(".")
        if f.lower().startswith(prefix) and f.lower().endswith(".mp3")
    ]
    if not tracks:
        raise RuntimeError(f"No files found matching '{prefix}*.mp3' in repo root")
    idx = abs(hash(theme)) % len(tracks)
    return tracks[idx]


# ---- STEP 3: BUILD DRAWTEXT TIMING ---------------------------------------

def build_line_timings(quote_text, total_duration, wrap_width=22):
    lines = textwrap.wrap(quote_text, width=wrap_width)
    char_counts = [len(l) for l in lines]
    total_chars = sum(char_counts) or 1

    timings = []
    t = 0.0
    for line, chars in zip(lines, char_counts):
        dur = total_duration * (chars / total_chars)
        timings.append((line, t, t + dur))
        t += dur
    return timings


def escape_drawtext(text):
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019")


# ---- STEP 4: RENDER VIDEO -------------------------------------------------

def render_video(theme, timings, total_duration, music_path, narration_path, out_path):
    tail_pad = 1.0
    video_duration = total_duration + tail_pad

    line_spacing = 110
    total_block_h = line_spacing * len(timings)
    start_y = (H - total_block_h) // 2

    drawtext_filters = []
    for i, (line, start, end) in enumerate(timings):
        safe = escape_drawtext(line)
        y = start_y + i * line_spacing
        drawtext_filters.append(
            f"drawtext=fontfile={SERIF_BOLD}:text='{safe}':fontcolor={TEXT_COLOR}:"
            f"fontsize=72:x=(w-text_w)/2:y={y}:"
            f"enable='between(t,{start:.2f},{end + 0.3:.2f})':"
            f"alpha='if(lt(t,{start + 0.15:.2f}),(t-{start:.2f})/0.15,1)'"
        )

    tag_text = escape_drawtext(theme.upper())
    header = (
        f"drawtext=fontfile={SANS}:text='{tag_text}':fontcolor={ACCENT}:fontsize=34:"
        f"x=90:y=150"
    )
    footer_title = (
        f"drawtext=fontfile={SANS}:text='THE ART OF BECOMING':fontcolor={TEXT_COLOR}:"
        f"fontsize=38:x=(w-text_w)/2:y=h-210"
    )
    footer_author = (
        f"drawtext=fontfile={SANS}:text='ARYAN AGRAWAL':fontcolor=0x969692:fontsize=30:"
        f"x=(w-text_w)/2:y=h-155"
    )

    all_filters = [header, footer_title, footer_author] + drawtext_filters
    vf_chain = ",".join(all_filters)

    filter_complex = (
        f"color=c={BG}:s={W}x{H}:d={video_duration}[bg];"
        f"[bg]{vf_chain}[v];"
        f"[1:a]volume=1.0[narration];"
        f"[2:a]volume=0.18,aloop=loop=-1:size=2e9,atrim=0:{video_duration}[music];"
        f"[narration][music]amix=inputs=2:duration=first:dropout_transition=2[a]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:d={video_duration}",
        "-i", narration_path,
        "-i", music_path,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-t", str(video_duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


# ---- MAIN -----------------------------------------------------------------

def make_reel(quote, theme, index):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    narration_path = f"/tmp/narration_{index}.mp3"
    out_path = f"{OUTPUT_DIR}/reel_{index:02d}.mp4"

    print(f"[{index}] Generating narration...")
    generate_narration(quote, narration_path)
    duration = get_audio_duration(narration_path)

    print(f"[{index}] Narration duration: {duration:.2f}s. Picking music...")
    music_path = pick_music(theme)

    print(f"[{index}] Building timings and rendering...")
    timings = build_line_timings(quote, duration)
    render_video(theme, timings, duration, music_path, narration_path, out_path)

    print(f"[{index}] Done: {out_path}")
    return out_path


if __name__ == "__main__":
    with open("quotes.json") as f:
        quotes = json.load(f)

    # For now, only render quotes whose theme maps to the "dramatic" mood,
    # since only dramatic_*.mp3 tracks have been uploaded so far.
    dramatic_themes = {
        theme for theme, mood in THEME_TO_MOOD.items() if mood == "dramatic"
    }

    dramatic_quotes = [q for q in quotes if q["theme"] in dramatic_themes]

    if not dramatic_quotes:
        print("No quotes found with a dramatic-mapped theme. Nothing to render.")

    for i, q in enumerate(dramatic_quotes, start=1):
        make_reel(q["quote"], q["theme"], i)
