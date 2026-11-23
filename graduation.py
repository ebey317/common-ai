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


def profile():
    return _json(PROFILE, {})


def _save_profile(prof):
    tmp = PROFILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(prof, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, PROFILE)


# A retirement is a CLAIM ABOUT THE WORLD, and the world moves. Retiring the
# job search because you are employed is correct until the day you are not.
# So retirement is never permanent-by-default: every status run re-checks it,
# and any layer whose reason has gone is reported as stale and woken.
def stale_retirements(prof, st):
    """Retired layers whose retire condition no longer holds."""
    out = []
    for name, spec in definitions().items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        if st.get(name, {}).get("state", spec.get("state", "on")) == "on":
            continue
        if not spec.get("check"):
            continue          # statement-only layers cannot be rechecked
        met, why = evaluate(name, spec, prof, st)
        if not met:
            out.append((name, why))
    return out


def cmd_wake(layer):
    """Bring back a retired layer whose reason no longer holds."""
    spec = definitions().get(layer)
    if not isinstance(spec, dict):
        print("unknown layer %r. known: %s"
              % (layer, ", ".join(n for n in definitions() if not n.startswith("_"))))
        return 2
    st = state()
    if st.get(layer, {}).get("state", "on") != "off":
        print("%s is already on - nothing to wake." % layer)
        return 0

    prof = profile()
    met, why = evaluate(layer, spec, prof, st)
    if met and spec.get("check"):
        print("%s stays retired: %s" % (layer, why))
        print("  The condition that retired it still holds. Restoring is still")
        print("  free - use --restore if you want it back anyway.")
        return 1

    st.setdefault(layer, {})
    st[layer]["state"] = "on"
    st[layer]["restored"] = date.today().isoformat()
    st[layer]["woke_because"] = why
    _save_state(st)
    print("woke %s." % layer)
    print("  because: %s" % why)
    print("  restored: %s" % st[layer]["restored"])
    return 0


def cmd_employment_ended(employer, end_date):
    """Record that a job ended, then wake whatever that change un-retires.

    This is the counterpart to retiring: the same event that justifies turning
    the job search off justifies turning it back on, and doing only the first
    is how a system ends up confidently idle while someone is unemployed.
    """
    prof = profile()
    target = None
    for e in prof.get("employment", []):
        if e.get("end"):
            continue
        name = str(e.get("employer") or "")
        if employer and employer.lower() not in name.lower():
            continue
        target = e
        break

    if target is None:
        print("no current employment found%s."
              % (" matching %r" % employer if employer else ""))
        print("  Current jobs are the entries with no end date.")
        return 2

    target["end"] = end_date
    _save_profile(prof)
    print("recorded: %s ended %s" % (target.get("employer", "?"), end_date))

    woke = 0
    for name, why in stale_retirements(prof, state()):
        print("  %s was retired, but: %s" % (name, why))
        if cmd_wake(name) == 0:
            woke += 1
    if not woke:
        print("  no retired layer needed waking.")
    return 0


# ---------------------------------------------------------------- commands
def cmd_status():
    specs = definitions()
    st = state()
    prof = _json(PROFILE, {})

    print("=" * 70)
    print("  GRADUATION - what the system is still doing for you")
    print("=" * 70)

    on = off = 0
    stale = []
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
            # Recheck the reason. Skipping evaluate() for retired layers was
            # the bug: a retirement that stopped being true stayed silent.
            met, why = evaluate(name, spec, prof, st)
            if spec.get("check") and not met:
                stale.append((name, why))
                print("     STATUS      : STALE - %s" % why)
                print("     wake it     : python3 graduation.py --wake %s" % name)
            else:
                print("     still true  : %s" % why)
            continue
        met, why = evaluate(name, spec, prof, st)
        print("     retires when: %s" % spec.get("retire_when", "?"))
        print("     right now   : %s%s" % (why, "   <- condition MET" if met else ""))
        print("     needs you to say: \"%s\"" % spec.get("requires_statement", "?"))

    print("\n" + "-" * 70)
    print("  running: %d   |   retired: %d" % (on, off))
    if stale:
        print("  %d retired layer(s) no longer justified:" % len(stale))
        for n, why in stale:
            print("    %s - %s" % (n, why))
        print("  Wake them with --wake, or record the change with --employment-ended.")
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
    if "--employment-ended" in argv:
        i = argv.index("--employment-ended")
        employer = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else ""
        end_date = date.today().isoformat()
        if "--on" in argv:
            j = argv.index("--on")
            end_date = argv[j + 1] if j + 1 < len(argv) else end_date
        return cmd_employment_ended(employer, end_date)
    if "--wake" in argv:
        i = argv.index("--wake")
        return cmd_wake(argv[i + 1] if i + 1 < len(argv) else "")
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
