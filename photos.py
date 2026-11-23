#!/usr/bin/env python3
"""
COMMON AI - wardrobe photos
===========================
Asking for the pictures is the feature. Three slots, each with a job:

  full_body   silhouette - what actually fits you, not a size chart
  torso       shirt and jacket fit at the shoulder and sleeve
  face        colour and contrast, so the palette is yours and not a guess

You are being dressed, not looked at. The face shot exists to pick colours,
nothing else.

  python3 photos.py status
  python3 photos.py add full_body /path/to/photo.jpg
  python3 photos.py remove face

PRIVACY IS STRUCTURAL, NOT A SETTING:
  these are body photos. They live in this repo, on this machine, and are never
  uploaded - not to a hosted image API, not to a model provider, not anywhere.
  Any service that needs to "see" them is the wrong service. Local PIL and
  local model calls only.
"""

import json
import os
import shutil
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")
ASSETS = os.path.join(HERE, "assets", "wardrobe")

SLOTS = {
    "full_body": "silhouette - what fits, full length, plain background",
    "torso": "shirt fit at shoulder and sleeve, waist up",
    "face": "colour and contrast only - this picks the palette",
}

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic")


def _load():
    with open(PROFILE, encoding="utf-8") as fh:
        return json.load(fh)


def _save(p):
    """Write the profile atomically.

    A direct open(PROFILE, "w") truncates the file before the new JSON is
    written, so a crash or a full disk leaves an empty profile - the one file
    everything else reads. Write to a sibling temp file, fsync, then rename,
    which is atomic on the same filesystem.
    """
    tmp = PROFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(p, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, PROFILE)


def _wardrobe(prof):
    w = prof.setdefault("wardrobe", {})
    w.setdefault("_note", "Reference photos for styling. Local only, never uploaded.")
    w.setdefault("photos", {})
    for slot, why in SLOTS.items():
        w["photos"].setdefault(slot, {"path": None, "purpose": why, "added": None})
    return w


def cmd_status():
    prof = _load()
    w = _wardrobe(prof)
    print("=" * 68)
    print("  WARDROBE PHOTOS")
    print("=" * 68)

    have = 0
    for slot, why in SLOTS.items():
        rec = w["photos"][slot]
        path = rec.get("path")
        ok = bool(path) and os.path.exists(path)
        have += ok
        print("\n  [%s] %s" % ("OK " if ok else "MISSING", slot))
        print("     captures : %s" % why)
        if ok:
            print("     file     : %s  (%s)"
                  % (os.path.basename(path), rec.get("added")))
        else:
            print("     add with : python3 photos.py add %s /path/to/photo.jpg" % slot)

    print("\n" + "-" * 68)
    if have == len(SLOTS):
        print("  All three on file. Styling can work from real images.")
    elif have:
        print("  %d of %d. Partial works - missing slots only weaken the fit." % (have, len(SLOTS)))
    else:
        print("  0 of 3. The styling layer cannot start without at least full_body.")
    print("  Stored locally at %s - never uploaded." % ASSETS)
    return 0


def _managed_path(slot, path):
    """True only when path is a file THIS tool created for THIS slot.

    The profile only stores a string. If it ever holds a path outside
    assets/wardrobe - a user editing the JSON, an old layout, a symlink - then
    `remove` would delete the person's original photograph. Deleting is
    irreversible, so ownership of the file is proven before every unlink.
    """
    if not path:
        return False
    real = os.path.realpath(path)
    assets = os.path.realpath(ASSETS)
    if os.path.dirname(real) != assets:
        return False
    return os.path.basename(real).startswith(slot + ".")


def cmd_add(slot, src):
    if slot not in SLOTS:
        print("unknown slot %r. choose: %s" % (slot, ", ".join(SLOTS)))
        return 2
    if not os.path.exists(src):
        print("no file at %s" % src)
        return 2
    if not src.lower().endswith(IMAGE_EXT):
        print("not an image: %s" % src)
        return 2

    # Validate the profile BEFORE copying. Copying first and failing on save
    # leaves a private image on disk that nothing references or will clean up.
    try:
        prof = _load()
    except Exception as exc:
        print("cannot read profile.json (%s) - nothing copied." % str(exc)[:80])
        return 2
    w = _wardrobe(prof)
    prev = w["photos"][slot].get("path")

    os.makedirs(ASSETS, exist_ok=True)
    dest = os.path.join(ASSETS, "%s%s" % (slot, os.path.splitext(src)[1].lower()))
    shutil.copy2(src, dest)

    w["photos"][slot].update({"path": dest, "added": date.today().isoformat()})
    _save(prof)

    # Swapping face.jpg for face.png would otherwise leave the JPEG behind:
    # the profile only remembers the newest path, so `remove` would delete the
    # PNG and silently orphan the JPG.
    if prev and _managed_path(slot, prev) and os.path.realpath(prev) != os.path.realpath(dest):
        try:
            os.remove(prev)
            print("  replaced previous file: %s" % os.path.basename(prev))
        except OSError:
            pass

    print("added %s -> %s" % (slot, dest))
    print("  purpose: %s" % SLOTS[slot])
    print("  stays on this machine.")
    return 0


def cmd_remove(slot):
    try:
        prof = _load()
    except Exception as exc:
        print("cannot read profile.json (%s)" % str(exc)[:80])
        return 2
    w = _wardrobe(prof)
    rec = w["photos"].get(slot)
    if not rec or not rec.get("path"):
        print("%s is already empty." % slot)
        return 0

    p = rec["path"]
    if not _managed_path(slot, p):
        print("%s points at a file this tool did not create for this slot:" % slot)
        print("  %s" % p)
        print("  left untouched and still recorded. Delete it yourself if you mean to.")
        return 1

    if os.path.exists(p):
        os.remove(p)
    rec["path"] = None
    rec["added"] = None
    _save(prof)
    print("removed %s. The file is deleted, not just delisted." % slot)
    return 0


def main(argv):
    if len(argv) < 2 or argv[1] == "status":
        return cmd_status()
    if argv[1] == "add" and len(argv) >= 4:
        return cmd_add(argv[2], argv[3])
    if argv[1] == "remove" and len(argv) >= 3:
        return cmd_remove(argv[2])
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
