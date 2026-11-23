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
  110  a live interview invite - outranks everything, it is the whole point
   95  an opportunity closing within two weeks
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
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")
LEDGER = os.path.join(HERE, "ledger.csv")
INVENTORY = os.path.join(HERE, "inventory.json")
STATE = os.path.join(HERE, "intake_state.json")
STANDARDS = os.path.join(HERE, "standards.json")
OPPS = os.path.join(HERE, "opportunities.json")

ALIVE = {"applied", "aged"}


def _std():
    """Read the standards file. Thresholds live there, not in this module."""
    st = _json(STANDARDS, {})
    life = st.get("lifecycle", {})
    def v(key, default):
        node = life.get(key, {})
        return node.get("value", default) if isinstance(node, dict) else default
    return st, v("check_days", 90), v("expire_days", 180)


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
def s_interviews(rows):
    """A live interview outranks everything. It is the whole point of the search."""
    out = []
    for r in rows:
        if r.get("status") != "interview":
            continue
        note = (r.get("notes") or "").strip()
        out.append({
            "pri": 110, "kind": "live",
            "text": "%s wants you for %s." % (r.get("company"), r.get("role")),
            "action": (note + ".") if note else "Respond today - a live invite goes cold fast.",
        })
    return out


def s_bucket_holes(prof, rows, today, expire_days):
    """A bucket with nothing live is the highest-value thing to say."""
    out = []
    buckets = prof.get("buckets", {})
    for name, cfg in buckets.items():
        live = [r for r in rows
                if r.get("bucket") == name
                and r.get("status") in ALIVE
                and age(r, today) < expire_days]
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


def s_checks_due(rows, today, check_days, expire_days):
    out = []
    for r in rows:
        if r.get("status") not in ALIVE:
            continue
        a = age(r, today)
        if check_days <= a < expire_days:
            out.append({
                "pri": 90, "kind": "job",
                "text": "%s (%s) is %d days out with no answer." % (
                    r.get("company"), r.get("role"), a),
                "action": "Check it once: call, or reply to the confirmation email.",
            })
    return out


def s_expired(rows, today, expire_days):
    out = []
    for r in rows:
        if r.get("status") in ALIVE and age(r, today) >= expire_days:
            out.append({
                "pri": 80, "kind": "job",
                "text": "%s (%s) hit 180 days - that posting is dead." % (
                    r.get("company"), r.get("role")),
                "action": "Drop it and put a fresh one in the same bucket.",
            })
    return out


def s_idle(prof, rows, today, std):
    """Nothing moved in N days."""
    node = std.get("wellbeing", {}).get("idle_days", {})
    idle_days = int(node.get("value", 5) if isinstance(node, dict) else (node or 5))
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


def s_violations(std, rows):
    """Employers the owner will not work for.

    The never-list means DO NOT APPLY THERE - the owner was fired from them or
    they are not good people to work for. It does NOT mean the record is
    erased: application forms and background checks require full history, so a
    closed entry sitting in the ledger is history, not a rule breach. Only a
    LIVE application at a banned employer is the violation.
    """
    out = []
    # The public standards.json carries placeholder examples; the real list is
    # personal and lives in the gitignored profile. Merge both so a clone gets
    # the rule and the owner gets their actual names.
    banned = set(std.get("never_list_employers", {}).get("value", []))
    banned |= set(_json(PROFILE, {}).get("never_list_employers") or [])
    alive = {"applied", "aged", "interview"}
    for r in rows:
        company = r.get("company")
        if company not in banned or r.get("status") not in alive:
            continue
        out.append({
            "pri": 120, "kind": "RULE",
            "text": "%s is on your never-list and still has a live application."
                    % company,
            "action": "Close it out. The never-list means do not apply there - "
                      "not good people to work for, or they fired you. Closed "
                      "history stays in the ledger; forms require full disclosure.",
        })
    return out


def s_opportunities(today):
    """Money in. Grants and programs that are open, matching, and closing."""
    data = _json(OPPS, {})
    out = []
    for o in data.get("opportunities", []):
        if o.get("status") not in ("open", "eligible", "not_started"):
            continue
        dl = o.get("deadline")
        pri, when = 45, ""
        if dl:
            try:
                left = (date.fromisoformat(dl) - today).days
                if left < 0:
                    continue
                if left <= 14:
                    pri = 95
                    when = " - closes in %d day%s" % (left, "" if left == 1 else "s")
                else:
                    when = " - closes %s" % dl
            except Exception:
                when = ""
        amt = o.get("amount")
        head = "%s%s" % (o.get("name"), (" ($%s%s)" % (amt, when)) if amt else when)
        if not o.get("verified", False):
            head += " [unverified - check before relying on it]"
        out.append({
            "pri": pri, "kind": "money",
            "text": head,
            "action": o.get("next_action") or "Look at it and decide.",
        })
    return out


def s_money_blind(prof, today):
    """The honest one: name the suggestion it cannot make, and what fills it."""
    sp = prof.get("spending", {})
    hh = prof.get("household", {})
    ast = prof.get("assets", {})
    missing = []
    if not sp.get("recurring_costs"):
        missing.append("monthly bills")
    if not hh.get("adults") and not hh.get("children"):
        missing.append("how many people you feed")
    if not ast.get("vehicle"):
        missing.append("your vehicle")
    if not missing:
        return []
    return [{
        "pri": 40, "kind": "money",
        "text": "I can't find cheaper living for you yet - I'm missing %s." % ", ".join(missing),
        "action": "python3 intake.py fills it. Then this line becomes '$X/month, here are "
                  "the switches' instead of an apology.",
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
    std, check_days, expire_days = _std()
    today = date.today()
    items = []
    items += s_violations(std, rows)
    items += s_interviews(rows)
    items += s_bucket_holes(prof, rows, today, expire_days)
    items += s_checks_due(rows, today, check_days, expire_days)
    items += s_expired(rows, today, expire_days)
    items += s_idle(prof, rows, today, std)
    items += s_spend_window(prof, today)
    items += s_opportunities(today)
    items += s_money_blind(prof, today)
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
