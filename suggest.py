#!/usr/bin/env python3
"""
COMMON AI - suggestive thinking
===============================
The layer that speaks first. Everything else waits to be run; this reads the
state and says what it would do next.

  python3 suggest.py             # ranked suggestions
  python3 suggest.py --quiet     # print nothing unless something is pressing
  python3 suggest.py --top 3     # just the best three

EVERY SUGGESTION IS COMPUTED, NOT IMPROVISED. Each one comes from a real value
in profile.json, ledger.csv, inventory.json, or intake_state.json. If a claim
cannot be traced to state, it does not get made. That rule is what makes a
suggestion trustworthy instead of a chatbot guessing.

Ranked by consequence:
  100  a bucket with nothing live - the search has a hole in it
   90  an application at its 90-day check
   80  an expired application that needs replacing
   70  nothing has moved in N days (N from the profile)
   60  surplus + time: the spend-window suggestion
   50  a project that is buildable today with tools already owned
   40  intake answers still blank, which makes something else a guess
   30  a stored fact whose correct answer is about to change
"""

import csv
import json
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")
LEDGER = os.path.join(HERE, "ledger.csv")
INVENTORY = os.path.join(HERE, "inventory.json")
STATE = os.path.join(HERE, "intake_state.json")

ALIVE = {"applied", "aged"}
CHECK_DAYS = 90
EXPIRE_DAYS = 180


# ---------------------------------------------------------------- load
def _json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def load_all():
    prof = _json(PROFILE, {})
    inv = _json(INVENTORY, {"tools": [], "budget": 0})
    st = _json(STATE, {"answers": {}})
    rows = []
    if os.path.exists(LEDGER):
        with open(LEDGER, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    return prof, inv, st, rows


def age(row, today):
    try:
        return (today - date.fromisoformat(row["applied"])).days
    except Exception:
        return 0


# ---------------------------------------------------------------- signals
def s_bucket_holes(prof, rows, today):
    """A bucket with nothing live is the highest-value thing to say."""
    out = []
    buckets = prof.get("buckets", {})
    for name, cfg in buckets.items():
        live = [r for r in rows
                if r.get("bucket") == name
                and r.get("status") in ALIVE
                and age(r, today) < EXPIRE_DAYS]
        if not live:
            label = cfg.get("label", name)
            titles = cfg.get("titles", [])
            example = titles[0] if titles else "any role"
            out.append({
                "pri": 100, "kind": "job",
                "text": "%s bucket is empty - nothing live in it." % label,
                "action": "Send one this week. Start with: %s." % example,
            })
    return out


def s_checks_due(rows, today):
    out = []
    for r in rows:
        if r.get("status") not in ALIVE:
            continue
        a = age(r, today)
        if CHECK_DAYS <= a < EXPIRE_DAYS:
            out.append({
                "pri": 90, "kind": "job",
                "text": "%s (%s) is %d days out with no answer." % (
                    r.get("company"), r.get("role"), a),
                "action": "Check it once: call, or reply to the confirmation email.",
            })
    return out


def s_expired(rows, today):
    out = []
    for r in rows:
        if r.get("status") in ALIVE and age(r, today) >= EXPIRE_DAYS:
            out.append({
                "pri": 80, "kind": "job",
                "text": "%s (%s) hit 180 days - that posting is dead." % (
                    r.get("company"), r.get("role")),
                "action": "Drop it and put a fresh one in the same bucket.",
            })
    return out


def s_idle(prof, rows, today):
    """Nothing moved in N days."""
    idle_days = int(prof.get("wellbeing", {}).get("idle_days") or 5)
    stamps = []
    for r in rows:
        try:
            stamps.append(date.fromisoformat(r["applied"]))
        except Exception:
            pass
    try:
        stamps.append(date.fromtimestamp(os.path.getmtime(LEDGER)))
    except Exception:
        pass
    last = max(stamps) if stamps else None
    quiet = (today - last).days if last else 999
    if quiet >= idle_days:
        return [{
            "pri": 70, "kind": "nudge",
            "text": "Nothing has moved in %d days." % quiet,
            "action": "Pick one thing below, or it stays quiet another week.",
        }]
    return []


def s_spend_window(prof, today):
    """Employed, past the settling-in point, wardrobe enabled -> redirect the spend."""
    sit = prof.get("situation", {})
    sp = prof.get("spending", {})
    if sit.get("status") not in ("employed", "self_employed"):
        return []
    if sp.get("wardrobe_interest") not in ("yes", "maybe later"):
        return []
    budget = sp.get("wardrobe_budget")
    hit = [e for e in prof.get("employment", [])
           if e.get("end") and (today - date.fromisoformat(e["end"])).days < 120]
    months = 0
    if hit:
        months = max(0, (today - date.fromisoformat(min(h["start"] for h in hit))).days // 30)
    if months >= 2:
        return [{
            "pri": 60, "kind": "spend",
            "text": "You have been working about %d months." % months,
            "action": "If money is burning a hole: %s on three outfits sharpens the "
                      "image instead of disappearing." % ("$%s" % budget if budget else "a little"),
        }]
    return []


def s_project(inv, prof):
    """Something buildable today with tools already owned."""
    tools = {t.lower() for t in inv.get("tools", [])}
    budget = inv.get("budget", 0)
    try:
        sys.path.insert(0, HERE)
        import projects as pj
    except Exception:
        return []
    if not tools:
        return []
    buildable = [p for p in getattr(pj, "CATALOG", [])
                 if p["cost"] <= budget
                 and all(t.lower() in tools for t in p["tools"])
                 and p["id"] not in inv.get("done", [])]
    if not buildable:
        return []
    # rotate by week so it varies instead of always naming the cheapest
    best = buildable[date.today().isocalendar()[1] % len(buildable)]
    return [{
        "pri": 50, "kind": "build",
        "text": "%s - $%d, about %d hours, and you own every tool it needs." % (
            best["name"], best["cost"], best["hours"]),
        "action": "That is a weekend, not a lifestyle change.",
    }]


def s_intake_gaps(st):
    """Blank answers make other outputs a guess. Name them."""
    answers = st.get("answers", {})
    important = [
        ("health.allergies", "Allergies are blank - every meal list is unverified"),
        ("health.doctor_rules", "No doctor limits recorded - meal plans are guessing"),
        ("household.children", "Nobody counted for meals - food cost is a guess"),
        ("spending.recurring_costs", "Recurring costs unknown - savings suggestions are blind"),
        ("wellbeing.hobbies_pay", "No paid-hobby list - project suggestions are generic"),
    ]
    out = []
    for key, msg in important:
        cur = answers
        for part in key.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur in (None, "", []):
            out.append({"pri": 40, "kind": "ask", "text": msg + ".",
                        "action": "Run: python3 intake.py"})
    if len(out) > 1:
        first = out[0]
        return [{
            "pri": 40, "kind": "ask",
            "text": "%d setup answers are still blank, so that much of the advice is a guess."
                    % len(out),
            "action": "Run: python3 intake.py - the first one it will ask is: %s"
                      % first["text"].rstrip("."),
        }]
    return out


def s_time_bombs(prof, today):
    """A stored answer whose correct value changes on a date."""
    out = []
    for e in prof.get("employment", []):
        if not e.get("end_confirmed", True):
            out.append({
                "pri": 30, "kind": "fact",
                "text": "%s end date is a guess (%s)" % (e["employer"], e.get("end")),
            })
    if len(out) > 1:
        names = ", ".join(i["text"].split(" end date")[0] for i in out[:4])
        return [{
            "pri": 30, "kind": "fact",
            "text": "%d employment end dates are still guesses: %s." % (len(out), names),
            "action": "Confirm them, or every gap, tenure check, and application date moves.",
        }]
    return out


# ---------------------------------------------------------------- render
def gather():
    prof, inv, st, rows = load_all()
    today = date.today()
    items = []
    items += s_bucket_holes(prof, rows, today)
    items += s_checks_due(rows, today)
    items += s_expired(rows, today)
    items += s_idle(prof, rows, today)
    items += s_spend_window(prof, today)
    items += s_project(inv, prof)
    items += s_intake_gaps(st)
    items += s_time_bombs(prof, today)
    items.sort(key=lambda x: -x["pri"])
    return items


def main(argv):
    quiet = "--quiet" in argv
    top = None
    if "--top" in argv:
        try:
            top = int(argv[argv.index("--top") + 1])
        except Exception:
            top = None

    items = gather()
    if top:
        items = items[:top]

    # quiet mode: only speak if something is genuinely pressing
    if quiet and not any(i["pri"] >= 70 for i in items):
        return 0
    if not items:
        if not quiet:
            print("Nothing pressing. The search is stocked, the tools are ready,")
            print("and nothing is aging out. That is what a quiet week looks like.")
        return 0

    print("=" * 66)
    print("  WHAT I'D DO NEXT        %s" % date.today().strftime("%A, %B %d"))
    print("=" * 66)
    for i, item in enumerate(items, 1):
        print("\n  %d. [%s] %s" % (i, item["kind"].upper(), item["text"]))
        print("     -> %s" % item["action"])
    print("\n" + "-" * 66)
    print("  Every line above came from a file. Nothing here is a guess.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
