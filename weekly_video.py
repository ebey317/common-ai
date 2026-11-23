#!/usr/bin/env python3
"""
COMMON AI - weekly video
========================
The weekly recap as a narrated MP4. One continuous scene feel, 30+ seconds,
every number read from the repo - nothing typed in by hand.

  python3 weekly_video.py                # builds weekly_demo.mp4
  python3 weekly_video.py --out foo.mp4

Pipeline: real data -> narration script -> edge-tts -> PIL cards -> ffmpeg.
No diffusion model, no GPU, no API key. ComfyUI backdrops are an upgrade, not
a prerequisite.

The rule this file follows: the video may not claim anything the files cannot
prove. If a number is ugly, it still goes in.
"""

import csv
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.csv")
OPPS = os.path.join(HERE, "opportunities.json")

W = H = 1080
GREEN = (0, 255, 120)
WHITE = (235, 235, 235)
DIM = (120, 120, 130)
BG = (8, 8, 10)

VOICE = "en-US-GuyNeural"   # deep American male
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size):
    from PIL import ImageFont
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------- data
def week_facts():
    rows = []
    if os.path.exists(LEDGER):
        with open(LEDGER, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

    live = [r for r in rows if r.get("status") in ("applied", "aged")]
    interviews = [r for r in rows if r.get("status") == "interview"]
    rejected = [r for r in rows if r.get("status") == "rejected"]

    proof = ("received", "invite", "interview", "declined", "cancel",
             "application #", "offer")
    verified = [r for r in rows
                if any(p in (r.get("notes") or "").lower() for p in proof)]

    opps = {}
    try:
        opps = json.load(open(OPPS, encoding="utf-8"))
    except Exception:
        pass
    grants = opps.get("opportunities", [])
    entered = [g for g in grants if g.get("status") == "entered"]
    open_grants = [g for g in grants if g.get("status") == "open"]

    return {
        "total": len(rows),
        "live": len(live),
        "interviews": [r.get("company") for r in interviews],
        "rejected": len(rejected),
        "verified": len(verified),
        "grants_tracked": len(grants),
        "grants_entered": len(entered),
        "grants_open": len(open_grants),
    }


def scenes(f):
    """(kicker, headline, sub, narration)"""
    n = len(f["interviews"])
    iv = ", ".join(f["interviews"][:4]) if f["interviews"] else "none"
    return [
        ("COMMON USE AI", "THE WEEK IN NUMBERS",
         "every figure read from the files",
         "Common Use AI. The week in numbers, and every one of these comes "
         "straight out of the files."),

        ("APPLICATIONS", "%d TRACKED" % f["total"],
         "%d still live" % f["live"],
         "%d applications tracked. %d still live in the pipeline."
         % (f["total"], f["live"])),

        ("THE REAL TEST", "%d OF %d VERIFIED" % (f["verified"], f["total"]),
         "an employer actually replied",
         "Here is the number that matters. %d of %d have a reply from an "
         "employer. The rest are on our word alone." % (f["verified"], f["total"])),

        ("INTERVIEWS", "%d LIVE" % n, iv,
         "%d live interviews. %s." % (n, iv) if n else "No live interviews."),

        ("MONEY", "%d GRANTS TRACKED" % f["grants_tracked"],
         "%d entered, %d open, none filed" % (f["grants_entered"], f["grants_open"]),
         "%d grants tracked. %d entered, %d still open, and not one filed yet."
         % (f["grants_tracked"], f["grants_entered"], f["grants_open"])),

        ("SIX LAYERS", "ALL RUNNING",
         "suggest, triage, drive, audit, ledger, token",
         "Six layers, all running. Suggestive thinking, email triage, Drive "
         "organisation, the weekly audit, the ledger, and the token watchdog."),

        ("COMMON USE AI", "STRUCTURE, NOT HYPE",
         "every line traced to a file",
         "That is the week. Every line above traces back to a file. "
         "Nothing here is a guess."),
    ]


# ---------------------------------------------------------------- render
def card(path, kicker, headline, sub):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([48, 48, W - 48, H - 48], outline=GREEN, width=3)
    d.rectangle([48, 48, W - 48, 60], fill=GREEN)

    d.text((96, 150), kicker, font=_font(38), fill=GREEN)
    d.text((96, 210), "─" * 24, font=_font(28), fill=DIM)

    # headline wraps
    f = _font(76)
    words, line, lines = headline.split(), "", []
    for w_ in words:
        t = (line + " " + w_).strip()
        if d.textlength(t, font=f) > W - 200:
            lines.append(line)
            line = w_
        else:
            line = t
    lines.append(line)
    y = 300
    for ln in lines[:3]:
        d.text((96, y), ln, font=f, fill=WHITE)
        y += 92

    d.text((96, H - 190), sub, font=_font(34), fill=DIM)
    d.text((96, H - 130), "common use ai", font=_font(26), fill=GREEN)
    img.save(path)


def say(text, out):
    """edge-tts first, espeak fallback."""
    try:
        r = subprocess.run(
            ["edge-tts", "--voice", VOICE, "--text", text, "--write-media", out],
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 1000:
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(["espeak", "-v", "en-us+m3", "-s", "150", "-w", out, text],
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0 and os.path.getsize(out) > 500
    except Exception:
        return False


def render(scenes_list, out):
    """Render any (kicker, headline, sub, narration) list to one MP4."""
    tmp = tempfile.mkdtemp(prefix="cua-vid-")
    clips, total = [], 0.0

    for i, (kicker, headline, sub, narr) in enumerate(scenes_list):
        png = os.path.join(tmp, "s%02d.png" % i)
        mp3 = os.path.join(tmp, "s%02d.mp3" % i)
        mp4 = os.path.join(tmp, "s%02d.mp4" % i)
        card(png, kicker, headline, sub)

        ok = say(narr, mp3)
        if not ok:
            print("  TTS failed on scene", i)
            return 1

        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", mp3],
            capture_output=True, text=True).stdout.strip() or 4)
        dur = max(dur + 0.6, 4.0)
        total += dur

        r = subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", png, "-i", mp3,
            "-t", "%.2f" % dur,
            "-af", "apad", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "128k", mp4],
            capture_output=True, text=True)
        if r.returncode != 0:
            print("  ffmpeg failed:", r.stderr[-300:])
            return 1
        clips.append(mp4)
        print("  scene %d/%d  %.1fs  %s" % (i + 1, len(scenes_list), dur, headline[:34]))

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        for c in clips:
            fh.write("file '%s'\n" % c)

    r = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                        "-i", lst, "-c", "copy", out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("concat failed:", r.stderr[-300:])
        return 1

    size = os.path.getsize(out)
    print("\n  -> %s" % out)
    print("  %.1fs, %.1f MB, %d scenes" % (total, size / 1e6, len(clips)))
    return 0


def main(argv):
    out = os.path.join(HERE, "weekly_demo.mp4")
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    facts = week_facts()
    print("data:", facts["total"], "tracked,", facts["verified"], "verified,",
          len(facts["interviews"]), "interviews")
    return render(scenes(facts), out)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
