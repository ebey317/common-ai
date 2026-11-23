#!/usr/bin/env python3
"""
COMMON AI - weekly audit
========================
suggest.py asks "what should I do next?"  This asks "is what I have still TRUE?"

A suggestion engine can be perfectly healthy while every fact under it has
rotted. That is the failure this file exists to catch, and it is the one that
already bit once: a document asserting "no employment gaps of six months" that
had quietly become false.

  python3 audit.py            # full report
  python3 audit.py --brief    # only P0/P1, the lines that need action

Checks, in order of what a mistake costs:

  1. TIME BOMBS   every fixed-answer rule, recomputed against today
  2. DRIFT        one fact, two files, different values
  3. LIFECYCLE    applications crossing 90/180, applied-but-never-confirmed
  4. UNLOGGED     inbox activity no record reflects
  5. STANDARDS    rules enforced on nobody's authority
  6. LAYERS       what was supposed to run and did not

Six is deliberate. An audit that cannot tell you a layer went dark is just
another silent layer - email triage sat dead for twelve days and nothing said
a word.

Everything here is computed. No model is called, no document is edited, and a
clean week prints two lines rather than a wall.
"""

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")
LEDGER = os.path.join(HERE, "ledger.csv")
STANDARDS = os.path.join(HERE, "standards.json")
OPPS = os.path.join(HERE, "opportunities.json")
PULSE_STATE = os.path.join(HERE, ".pulse_state.json")

ALIVE = {"applied", "aged"}
LONG_TERM_UNEMPLOYED_WEEKS = 27   # WOTC-style long-term unemployment threshold


def _json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _days(d):
    """Days since an ISO date, or None if unparseable."""
    try:
        return (date.today() - date.fromisoformat(str(d)[:10])).days
    except Exception:
        return None


def _age(d):
    """Days since an ISO date, treating unparseable as very old.

    NOTE: never write `_days(x) or FALLBACK`. An application submitted TODAY
    returns 0, which is falsy, so `or 999` silently drops it and today's work
    never counts toward any window. Zero is a valid age; only None is missing.
    """
    age = _days(d)
    return 999 if age is None else age


def finding(sev, area, text, action):
    return {"sev": sev, "area": area, "text": text, "action": action}


# ---------------------------------------------------------------- 1. time bombs
def check_time_bombs(prof):
    """Recompute every fixed-answer rule. Name the date it flips."""
    out = []
    ends = []
    for e in prof.get("employment", []):
        d = e.get("end")
        if d:
            ends.append((date.fromisoformat(str(d)[:10]), e.get("employer", "?")))
    if not ends:
        return out

    last_end, last_employer = max(ends)
    weeks = (date.today() - last_end).days // 7
    flip = last_end + timedelta(weeks=LONG_TERM_UNEMPLOYED_WEEKS)
    days_to_flip = (flip - date.today()).days

    if days_to_flip < 0:
        out.append(finding(
            "P0", "timebomb",
            "The long-term-unemployment answer is already YES. It flipped on %s "
            "(%d weeks since %s)." % (flip.isoformat(), weeks, last_employer),
            "Any WOTC or tax-credit question now answers YES. Any document still "
            "saying NO is wrong."))
    elif days_to_flip <= 30:
        out.append(finding(
            "P1", "timebomb",
            "The long-term-unemployment answer flips to YES in %d days, on %s "
            "(%d weeks since %s)." % (days_to_flip, flip.isoformat(), weeks, last_employer),
            "Rewrite it as a computation before that date, not a fixed answer."))

    # a document asserting a fixed unemployment length is a bomb by definition
    for doc in prof.get("documents", []) or []:
        note = str(doc).lower()
        if "gap" in note and ("no " in note or "never" in note):
            out.append(finding(
                "P1", "timebomb",
                "Document %r asserts a fixed no-gap answer." % doc,
                "Fixed answers decay. Replace with a date-driven computation."))
    return out


# ---------------------------------------------------------------- 2. drift
def check_drift(prof, rows, std):
    out = []

    # guessed end dates - every date downstream moves if these are wrong
    guesses = [e.get("employer") for e in prof.get("employment", [])
               if e.get("end_confirmed") is False]
    if guesses:
        out.append(finding(
            "P1", "drift",
            "%d employment end dates are unconfirmed: %s."
            % (len(guesses), ", ".join(str(g) for g in guesses[:5])),
            "Each one moves a gap, a tenure check, and every application date."))

    # never-list appearing in the ledger
    banned = set(std.get("never_list_employers", {}).get("value", []))
    hits = sorted({r.get("company") for r in rows if r.get("company") in banned})
    if hits:
        out.append(finding(
            "P0", "drift",
            "Never-list employers present in the ledger: %s." % ", ".join(hits),
            "Remove them; the work belongs in the staffing block, unnamed."))

    # volume: standard vs what is actually happening
    per_bucket = std.get("lifecycle", {}).get("per_bucket_per_run", {})
    target = per_bucket.get("value") if isinstance(per_bucket, dict) else None
    if target:
        recent = [r for r in rows if _age(r.get("applied")) <= 7]
        if len(recent) > target * 4:
            out.append(finding(
                "P2", "drift",
                "%d applications in the last 7 days against a standard of %d per "
                "bucket per run." % (len(recent), target),
                "Either the standard is stale or the volume is. Reconcile it."))
    return out


# ---------------------------------------------------------------- 3. lifecycle
def check_lifecycle(rows, std):
    out = []
    check = std.get("lifecycle", {}).get("check_days", {})
    expire = std.get("lifecycle", {}).get("expire_days", {})
    c = check.get("value", 90) if isinstance(check, dict) else 90
    x = expire.get("value", 180) if isinstance(expire, dict) else 180

    stale, dead = [], []
    for r in rows:
        if r.get("status") not in ALIVE:
            continue
        d = _days(r.get("applied"))
        if d is None:
            continue
        if d >= x:
            dead.append("%s (%dd)" % (r.get("company"), d))
        elif d >= c:
            stale.append("%s (%dd)" % (r.get("company"), d))

    if dead:
        out.append(finding(
            "P1", "lifecycle",
            "%d applications are past %d days: %s." % (len(dead), x, ", ".join(dead[:4])),
            "Those postings are gone. Replace them, do not re-tap them."))
    if stale:
        out.append(finding(
            "P2", "lifecycle",
            "%d applications are due a %d-day check." % (len(stale), c),
            "One contact each, then close or keep."))

    # applied but never confirmed - the status nobody maintains
    unconfirmed = [r for r in rows
                   if r.get("status") == "applied" and not (r.get("notes") or "").strip()]
    if len(unconfirmed) >= 5:
        out.append(finding(
            "P2", "lifecycle",
            "%d applications have no note at all - nobody knows if they landed."
            % len(unconfirmed),
            "A blank note means no confirmation was ever recorded."))
    return out


# ---------------------------------------------------------------- 4. unlogged
def check_unlogged(rows):
    """Inbox activity the record does not reflect. Degrades loudly."""
    out = []
    triage = os.path.join(HERE, "layers", "email", "triage.py")
    if not os.path.exists(triage):
        out.append(finding(
            "P1", "unlogged",
            "Email triage layer is missing, so inbox activity cannot be checked.",
            "Restore layers/email/triage.py."))
        return out

    newest = None
    for r in rows:
        d = _days(r.get("applied"))
        if d is not None:
            newest = d if newest is None else min(newest, d)
    if newest is not None and newest > 7:
        out.append(finding(
            "P1", "unlogged",
            "No application logged in %d days - the ledger may be behind the inbox."
            % newest,
            "Check mail for replies that change a status, then log them."))
    return out


# ---------------------------------------------------------------- 5. standards
def check_standards(std):
    out = []

    def walk(node, path=""):
        if isinstance(node, dict):
            if "value" in node:
                yield path, node
                return
            for k, v in node.items():
                if not k.startswith("_"):
                    yield from walk(v, "%s.%s" % (path, k) if path else k)
        elif isinstance(node, list):
            yield path, {"value": node}

    unsourced = [p for p, n in walk(std) if not n.get("source")]
    if unsourced:
        out.append(finding(
            "P1", "standards",
            "%d rules are enforced with no source: %s."
            % (len(unsourced), ", ".join(unsourced[:4])),
            "A rule nobody can justify cannot be corrected. Add a source or drop it."))
    return out


# ---------------------------------------------------------------- 6. layers
def check_layers(std):
    out = []
    state = _json(PULSE_STATE, {})
    cad = std.get("cadence", {})
    if not state:
        return [finding(
            "P1", "layers",
            "Pulse has never recorded a run - every layer is unverified.",
            "Run: python3 pulse.py")]

    now = datetime.now().timestamp()
    for name, spec in cad.items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        every = int(spec.get("every_minutes", 1440)) * 60
        last = state.get(name, {}).get("last", 0)
        if not last:
            continue
        gap = now - last
        if gap > every * 2:
            out.append(finding(
                "P1", "layers",
                "%s has not run in %.1f days (expected every %d min)."
                % (name, gap / 86400, every // 60),
                "A dark layer is silence, not health. Find out why."))
    return out


# ---------------------------------------------------------------- render
def gather():
    prof = _json(PROFILE, {})
    std = _json(STANDARDS, {})
    rows = []
    if os.path.exists(LEDGER):
        with open(LEDGER, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

    items = []
    items += check_time_bombs(prof)
    items += check_drift(prof, rows, std)
    items += check_lifecycle(rows, std)
    items += check_unlogged(rows)
    items += check_standards(std)
    items += check_layers(std)

    order = {"P0": 0, "P1": 1, "P2": 2}
    items.sort(key=lambda x: order.get(x["sev"], 9))
    return items, rows


def main(argv):
    brief = "--brief" in argv
    items, rows = gather()
    live = sum(1 for r in rows if r.get("status") in ALIVE)
    today = date.today().strftime("%A, %B %d, %Y")

    shown = [i for i in items if i["sev"] in ("P0", "P1")] if brief else items

    print("=" * 72)
    print("  WEEKLY AUDIT - is the record still true?")
    print("  %s   |   %d live applications" % (today, live))
    print("=" * 72)

    if not shown:
        print("\n  Clean. No wrong facts, no decayed rules, every layer ran.")
        print("  Nothing here needs you this week.")
        return 0

    for i in shown:
        print("\n  [%s] %s" % (i["sev"], i["area"].upper()))
        print("    %s" % i["text"])
        print("    -> %s" % i["action"])

    p0 = sum(1 for i in items if i["sev"] == "P0")
    p1 = sum(1 for i in items if i["sev"] == "P1")
    p2 = sum(1 for i in items if i["sev"] == "P2")
    print("\n" + "-" * 72)
    print("  %d wrong now (P0) | %d decaying (P1) | %d hygiene (P2)" % (p0, p1, p2))
    if brief:
        print("  Brief mode: P2 hygiene items hidden.")
    return 1 if p0 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
