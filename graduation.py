#!/usr/bin/env python3
"""
COMMON AI - graduation
======================
Every layer runs by default. Turning one OFF is not a toggle - it is a claim
that the problem it solves is gone, and it has to be said in words.

  python3 graduation.py                  # what's on, what's retired, level
  python3 graduation.py --propose        # layers whose retire condition is met
  python3 graduation.py --retire job_search --statement "I have a job and I'm keeping it"
  python3 graduation.py --restore job_search

THE ASYMMETRY IS DELIBERATE:
  turning OFF costs a sentence and gets recorded with a date
  turning ON  is free and instant

A safety net you must argue with to restore is a trap. A net you can't turn off
without saying why is dignity. Only one direction gets friction.

Layers switched off are the measure of progress: all on = crisis, all off = BO.
Turning one off does NOT make the underlying fact true, so the ones that can be
checked mechanically are checked anyway, and a claim that contradicts them is
flagged rather than honoured.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
STANDARDS = os.path.join(HERE, "standards.json")
PROFILE = os.path.join(HERE, "profile.json")
STATE = os.path.join(HERE, "layer_state.json")


def _json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _save_state(state):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def definitions():
    """Layer specs live in standards.json -> layers."""
    return _json(STANDARDS, {}).get("layers", {})


def state():
    return _json(STATE, {})


# ---------------------------------------------------------------- checks
def employment_days(prof):
    """Days in the current job, or None if not employed."""
    for e in prof.get("employment", []):
        if e.get("end"):
            continue
        start = e.get("start")
        if not start:
            continue
        try:
            return (date.today() - date.fromisoformat(str(start)[:10])).days
        except Exception:
            continue
    return None


def evaluate(layer, spec, prof, st):
    """Return (met, evidence) for a layer's retire condition."""
    check = spec.get("check")
    if not check:
        return False, "statement only - no mechanical proof exists"

    if check == "employed_days":
        need = int(spec.get("threshold_days", 90))
        days = employment_days(prof)
        if days is None:
            return False, "not employed, so the job search is still needed"
        return days >= need, "employed %d days (needs %d)" % (days, need)

    if check == "spend_on_record":
        costs = prof.get("spending", {}).get("recurring_costs", [])
        return bool(costs), ("%d recurring costs on record" % len(costs))

    return False, "unknown check %r" % check


# ---------------------------------------------------------------- commands
def cmd_status():
    specs = definitions()
    st = state()
    prof = _json(PROFILE, {})

    print("=" * 70)
    print("  GRADUATION - what the system is still doing for you")
    print("=" * 70)

    on = off = 0
    for name, spec in specs.items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        rec = st.get(name, {})
        running = rec.get("state", spec.get("state", "on")) == "on"
        on += running
        off += (not running)
        mark = "ON " if running else "OFF"
        print("\n  [%s] %s" % (mark, name))
        print("     solves      : %s" % spec.get("runs_when", "?"))
        if not running:
            print("     retired     : %s" % rec.get("off_since", "?"))
            print("     on your word: \"%s\"" % rec.get("off_claimed", "?"))
            continue
        met, why = evaluate(name, spec, prof, st)
        print("     retires when: %s" % spec.get("retire_when", "?"))
        print("     right now   : %s%s" % (why, "   <- condition MET" if met else ""))
        print("     needs you to say: \"%s\"" % spec.get("requires_statement", "?"))

    print("\n" + "-" * 70)
    print("  running: %d   |   retired: %d" % (on, off))
    if off == 0:
        print("  Level 0 - everything is on. This is the right place to start.")
    elif on == 0:
        print("  Every layer retired. The problems they solved are gone.")
        print("  This is the BO threshold: nothing left to handle.")
    else:
        print("  Level %d of %d. Each retired layer is a problem no longer here."
              % (off, on + off))
    return 0


def cmd_propose():
    specs, st, prof = definitions(), state(), _json(PROFILE, {})
    rows = []
    for name, spec in specs.items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        if st.get(name, {}).get("state", "on") != "on":
            continue
        met, why = evaluate(name, spec, prof, st)
        if met:
            rows.append((name, why, spec.get("requires_statement", "")))

    if not rows:
        print("Nothing is ready to retire. Keep them running.")
        return 0
    print("READY TO RETIRE - each one needs a sentence from you, not a click:\n")
    for name, why, sentence in rows:
        print("  %s  (%s)" % (name, why))
        print("     if this is true, say: \"%s\"" % sentence)
        print("     -> python3 graduation.py --retire %s --statement \"%s\"\n"
              % (name, sentence))
    return 0


def cmd_retire(layer, statement):
    specs = definitions()
    spec = specs.get(layer)
    if not isinstance(spec, dict):
        print("no such layer: %s" % layer)
        return 2
    expected = (spec.get("requires_statement") or "").strip().lower()
    given = (statement or "").strip().lower().strip('"').strip("'")
    if not given:
        print("refusing: retiring %r needs a statement.\n  say: \"%s\""
              % (layer, spec.get("requires_statement", "")))
        return 2
    if expected and given != expected:
        print("refusing: that is not the claim this layer requires.")
        print("  it needs: \"%s\"" % spec.get("requires_statement", ""))
        return 2

    prof = _json(PROFILE, {})
    met, why = evaluate(layer, spec, prof, {})
    if spec.get("check") and not met:
        print("refusing: the record contradicts that claim.")
        print("  %s" % why)
        print("  Turning this off would not make it true.")
        return 2

    st = state()
    st[layer] = {
        "state": "off",
        "off_since": date.today().isoformat(),
        "off_claimed": statement.strip(),
        "evidence_at_retirement": why,
    }
    _save_state(st)
    print("retired: %s on %s" % (layer, st[layer]["off_since"]))
    print("  on your word: \"%s\"" % statement.strip())
    if spec.get("check"):
        print("  the record agrees: %s" % why)
    return 0


def cmd_restore(layer):
    st = state()
    if layer not in st:
        print("%s was never retired." % layer)
        return 0
    st[layer]["state"] = "on"
    st[layer]["restored"] = date.today().isoformat()
    _save_state(st)
    print("restored: %s. No statement needed - restoring is always free." % layer)
    return 0


def main(argv):
    if "--retire" in argv:
        i = argv.index("--retire")
        layer = argv[i + 1] if i + 1 < len(argv) else ""
        stmt = ""
        if "--statement" in argv:
            j = argv.index("--statement")
            stmt = argv[j + 1] if j + 1 < len(argv) else ""
        return cmd_retire(layer, stmt)
    if "--restore" in argv:
        i = argv.index("--restore")
        return cmd_restore(argv[i + 1] if i + 1 < len(argv) else "")
    if "--propose" in argv:
        return cmd_propose()
    return cmd_status()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
