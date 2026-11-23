#!/usr/bin/env python3
"""
COMMON AI - setup
=================
One command that answers "is this thing working, and what do I do next?"

Written for two readers at once: a person at a terminal, and an AI agent that
has just cloned the repo and needs to stand it up without guessing. Every line
is a check with a verdict, and the last line is the single next action.

  python3 setup.py            check the environment, then smoke-test the code
  python3 setup.py --check    environment only, no execution
  python3 setup.py --test     smoke-test only

Exit codes are meaningful, so an agent can branch on them:
  0  ready
  1  a check failed and the message says which
  2  usable, but the person still has to answer something (e.g. run intake)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

REQUIRED = [
    "intake.py", "profile.py", "ledger.py", "suggest.py", "audit.py",
    "standards.py", "standards.json", "pulse.py", "graduation.py",
    "projects.py", "receipt.py", "vault.py", "workspace.py", "photos.py",
    "sources.py", "profile.example.json",
]

ok_count = 0
fail = []


def say(state, name, note=""):
    global ok_count
    if state == "ok":
        ok_count += 1
    elif state == "fail":
        fail.append(name)
    print("  %-6s %-22s %s" % (state.upper(), name, note))


def check_python():
    v = sys.version_info
    if v < (3, 8):
        say("fail", "python", "%d.%d - needs 3.8 or newer" % (v[0], v[1]))
        return False
    say("ok", "python", "%d.%d.%d" % (v[0], v[1], v[2]))
    return True


def check_files():
    missing = [f for f in REQUIRED if not os.path.exists(os.path.join(HERE, f))]
    if missing:
        say("fail", "files", "missing: %s" % ", ".join(missing))
        return False
    say("ok", "files", "%d expected modules present" % len(REQUIRED))
    return True


def check_imports():
    broken = []
    for f in REQUIRED:
        if not f.endswith(".py"):
            continue
        path = os.path.join(HERE, f)
        r = subprocess.run([PY, "-c", "import ast,sys;ast.parse(open(sys.argv[1]).read())", path],
                           capture_output=True, text=True)
        if r.returncode != 0:
            broken.append(f)
    if broken:
        say("fail", "syntax", "will not parse: %s" % ", ".join(broken))
        return False
    say("ok", "syntax", "every module parses")
    return True


def check_state():
    prof = os.path.join(HERE, "profile.json")
    led = os.path.join(HERE, "ledger.csv")
    has_prof = os.path.exists(prof)
    say("ok" if has_prof else "need", "profile.json",
        "present" if has_prof else "not built yet - python3 intake.py creates it")
    if os.path.exists(led):
        with open(led, encoding="utf-8") as fh:
            rows = max(0, sum(1 for _ in fh) - 1)
        say("ok", "ledger.csv", "%d applications" % rows)
    else:
        say("ok", "ledger.csv", "empty - ledger.py add or ledger.py seed")
    return has_prof


def smoke():
    """Run the real commands in a throwaway copy, on seed data.

    Executed in a temp dir on purpose: a setup check must never touch the
    person's own profile or ledger, and it must still exercise real code paths
    rather than importing modules and calling it a test.
    """
    tmp = tempfile.mkdtemp(prefix="commonai-setup-")
    try:
        for f in os.listdir(HERE):
            src = os.path.join(HERE, f)
            if os.path.isfile(src) and (f.endswith(".py") or f.endswith(".json")):
                shutil.copy2(src, os.path.join(tmp, f))

        tests = [
            ("ledger seed", [PY, "ledger.py", "seed"], None),
            ("ledger report", [PY, "ledger.py", "report"], "DREAM"),
            ("suggest", [PY, "suggest.py"], None),
            ("audit", [PY, "audit.py", "--brief"], None),
            ("pulse status", [PY, "pulse.py", "--status"], "PULSE STATUS"),
            ("graduation", [PY, "graduation.py"], "GRADUATION"),
            ("standards", [PY, "standards.py"], None),
        ]
        for name, cmd, expect in tests:
            r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, timeout=120)
            out = (r.stdout or "") + (r.stderr or "")
            if r.returncode not in (0, 1):
                say("fail", name, "exit %d: %s" % (r.returncode, out.strip().splitlines()[:1]))
            elif expect and expect not in out:
                say("fail", name, "ran but did not print %r" % expect)
            elif "Traceback" in out:
                say("fail", name, "raised: %s" % out.strip().splitlines()[-1][:60])
            else:
                say("ok", name, "ran")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def next_step(has_prof):
    print("\n" + "-" * 66)
    if fail:
        print("  NOT READY - %d check(s) failed: %s" % (len(fail), ", ".join(fail)))
        print("  Fix those before using this. Nothing else runs correctly until they do.")
        return 1
    if not has_prof:
        print("  NEXT: run the setup interview")
        print("\n      python3 intake.py\n")
        print("  It asks ~33 questions and writes profile.json, which every other")
        print("  module reads. Answers can be corrected later; it is resumable.")
        print("  Then:  python3 profile.py resume trade   (see what it made)")
        return 2
    print("  READY. profile.json exists, so the whole loop works:")
    print("\n      python3 suggest.py        what needs you today")
    print("      python3 audit.py --brief  is the record still true")
    print("      python3 vault.py --backup put the record in your own cloud")
    return 0


def main(argv):
    print("=" * 66)
    print("  COMMON AI - setup check")
    print("=" * 66)
    only_check = "--check" in argv
    only_test = "--test" in argv

    if not only_test:
        check_python()
        check_files()
        has_prof = check_state()
    else:
        has_prof = os.path.exists(os.path.join(HERE, "profile.json"))

    if not only_check:
        print("\n  smoke test (in a temp copy - your files are not touched)")
        smoke()

    return next_step(has_prof)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
