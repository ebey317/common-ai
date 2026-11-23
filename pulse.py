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
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STANDARDS = os.path.join(HERE, "standards.json")
STATE = os.path.join(HERE, ".pulse_state.json")
PY = sys.executable


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


def cadence():
    try:
        with open(STANDARDS, encoding="utf-8") as fh:
            return json.load(fh).get("cadence", {})
    except Exception:
        return {}


# layer name -> (what it runs, is it built)
def layers():
    return {
        "suggest": (lambda: run([PY, "suggest.py", "--quiet"]), True),
        "ledger_age": (lambda: run([PY, "ledger.py", "age"]), True),
        "token_watch": (lambda: run(["bash", os.path.expanduser(
            "~/.hermes/scripts/google_workspace_token_check.sh")]), True),
        "email_triage": (None, False),
        "drive_organize": (None, False),
        "weekly_audit": (None, False),
    }


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
        st[name] = {"last": time.time()}
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
