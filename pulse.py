#!/usr/bin/env python3
"""
COMMON AI - pulse
=================
The heartbeat the repo did not have.

Every "always on" behaviour used to live in the owner's personal cron, which
meant a customer who installed this got a folder of scripts and no clock. Pulse
is the repo's own clock: the host calls it as often as it likes (cron, systemd
timer, Task Scheduler, a loop) and pulse decides what is actually due.

  python3 pulse.py            # run whatever is due, say what happened
  python3 pulse.py --status   # what is due, what is resting, what is unbuilt
  python3 pulse.py --force suggest   # run one layer now regardless of clock

Cadence is NOT hardcoded here. It lives in standards.json under "cadence", so
changing how often email is triaged is a one-line data edit.

A layer this repo cannot do yet reports NOT BUILT rather than silently passing.
An honest empty is worth more than a fake green.
"""

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STANDARDS = os.path.join(HERE, "standards.json")
STATE = os.path.join(HERE, ".pulse_state.json")
LOCK = os.path.join(HERE, ".pulse.lock")
PY = sys.executable

# A pulse run that dies mid-flight must not wedge the scheduler forever, so a
# lock older than this is treated as abandoned and taken over.
LOCK_STALE_SECONDS = 1800


def acquire_lock():
    """One runner at a time, atomically.

    Two overlapping runs both read the state, both decide a layer is due, and
    both process the same messages before either writes a timestamp. Nothing
    errors - you just get the work done twice. O_CREAT|O_EXCL makes the claim
    atomic at the filesystem level, so only one caller can win it.
    """
    for attempt in (0, 1):
        try:
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if attempt:
                return False
            try:
                age = time.time() - os.path.getmtime(LOCK)
            except OSError:
                return False
            if age < LOCK_STALE_SECONDS:
                return False
            try:
                os.remove(LOCK)          # abandoned by a dead run
            except OSError:
                return False
            continue
        try:
            os.write(fd, str(os.getpid()).encode())
        finally:
            os.close(fd)
        return True
    return False


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_state(st):
    try:
        with open(STATE, "w", encoding="utf-8") as fh:
            json.dump(st, fh, indent=2)
    except Exception:
        pass


def fingerprint(name, out):
    """What counts as "the same message" for a layer. Dates, ages and one-time
    auth links change every run without meaning anything, so they are ignored:
    suggest compares its numbered items, every other layer its first line."""
    import hashlib
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if name == "suggest":
        key = [re.sub(r"\s+", " ", l) for l in lines if re.match(r"^\d+\.\s*\[", l)]
    elif name == "email_triage":
        # the listed messages only; spam counts drifting up must not re-send the cards
        key = [l for l in lines if l.startswith("- [") or "COULD NOT BE READ" in l]
    else:
        key = lines[:1]
    return hashlib.sha256("\n".join(key).encode()).hexdigest()[:16]


def cadence():
    try:
        with open(STANDARDS, encoding="utf-8") as fh:
            return json.load(fh).get("cadence", {})
    except Exception:
        return {}


# layer name -> (what it runs, is it built)
def layers():
    return {
        "suggest": (lambda: run([PY, "suggest.py", "--quiet", "--min-pri", "70"]), True),
        "ledger_age": (lambda: run([PY, "ledger.py", "age"]), True),
        "token_watch": (lambda: run(["bash", os.path.expanduser(
            "~/.hermes/scripts/google_workspace_token_check.sh")]), True),
        "email_triage": (lambda: run(["/usr/bin/python3", os.path.join("layers", "email", "cards.py")]), True),
        "drive_organize": (lambda: run([PY, os.path.join("layers", "clean",
                                                         "sensei_clean_cli.py"),
                                        "status"]), True),
        "weekly_audit": (lambda: run_tolerant([PY, "audit.py", "--brief"]), True),
    }


def run_tolerant(cmd):
    """Like run(), but exit 1 means "found something", not "broke"."""
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=180)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return (0 if p.returncode in (0, 1) else 1), out
    except Exception as exc:
        return 1, str(exc)


def run(cmd):
    try:
        p = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=120)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            return 1, (err or out or "exit %d with no output" % p.returncode)
        return 0, out
    except Exception as exc:
        return 1, str(exc)


def due_map(st, cad):
    now = time.time()
    due = {}
    for name, (fn, built) in layers().items():
        spec = cad.get(name)
        if not isinstance(spec, dict):
            continue
        every = int(spec.get("every_minutes", 1440)) * 60
        last = st.get(name, {}).get("last", 0)
        due[name] = {
            "due": (now - last) >= every,
            "built": built,
            "every_minutes": spec.get("every_minutes"),
            "last": last,
            "next_in_min": max(0, int((every - (now - last)) // 60)) if last else 0,
        }
    return due


def main(argv):
    # --status only reads, so it never takes the lock and is never blocked by a
    # run in progress.
    if "--status" in argv:
        return _run(argv)
    if not acquire_lock():
        print("another pulse run is already working - exiting clean.")
        print("  it owns the timestamps, so this run does nothing instead of")
        print("  repeating its work.")
        return 0
    try:
        return _run(argv)
    finally:
        release_lock()


def _run(argv):
    st = load_state()
    cad = cadence()
    due = due_map(st, cad)

    if "--status" in argv:
        print("=" * 70)
        print("  PULSE STATUS")
        print("=" * 70)
        for name, d in due.items():
            if not d["built"]:
                mark, note = "UNBUILT", "no code in this repo yet"
            elif d["due"]:
                mark, note = "DUE    ", "runs next pulse"
            else:
                mark, note = "resting", "next in ~%d min" % d["next_in_min"]
            print("  %-16s %s  every %-5s min   %s" % (
                name, mark, d["every_minutes"], note))
        print("\n  Cadence lives in standards.json -> cadence.")
        return 0

    force = None
    if "--force" in argv:
        i = argv.index("--force")
        if i + 1 < len(argv):
            force = argv[i + 1]

    ran, quiet, failed = [], [], []
    for name, (fn, built) in layers().items():
        d = due.get(name)
        if not d:
            continue
        if force and name != force:
            continue
        if not force and not d["due"]:
            continue
        if not built:
            quiet.append((name, "not built"))
            continue
        code, out = fn()  # type: ignore[misc]
        prev = st.get(name, {})
        st[name] = {"last": time.time(), "sent": prev.get("sent")}
        text = out or ""
        if text:
            fp = fingerprint(name, text)
            if fp == prev.get("sent") and not force:
                quiet.append((name, "unchanged"))   # said this already
                continue
            st[name]["sent"] = fp
        elif code == 0:
            st[name]["sent"] = None   # went quiet; a return of the issue is news
        if code == 0:
            if out:
                ran.append((name, out))
            else:
                quiet.append((name, "silent"))
        else:
            failed.append((name, out))

    save_state(st)

    spoke = False
    for name, out in ran:
        print("\n[%s]" % name)
        print(out)
        spoke = True
    for name, out in failed:
        print("\n[%s] FAILED" % name)
        print(out)
        spoke = True

    if not spoke and "--verbose" in argv:
        print("pulse: nothing pressing (%d layers silent, %d unbuilt)"
              % (len(quiet), sum(1 for n, _ in quiet if _ == "not built")))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
