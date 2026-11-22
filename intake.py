#!/usr/bin/env python3
"""
COMMON AI - the intake
======================
The one thing every layer reads from. Six sections, in the order that earns
the right to ask the next one. Resumable: quit halfway, come back, it picks up.

  python3 intake.py            # start or resume
  python3 intake.py --status   # where you left off
  python3 intake.py --reset    # start over
  python3 intake.py --render   # write profile.json from answers, change nothing else

THE RULE EVERY QUESTION OBEYS: it must feed something. If a question cannot
change an output, it does not get asked. That is the difference between being
taken care of and being interrogated.

THE HARD LINE ON HEALTH: this program asks what a doctor already decided.
It never decides what is healthy for a condition, and allergies are hard stops
that nothing downstream may override.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "intake_state.json")
PROFILE = os.path.join(HERE, "profile.json")

# ----------------------------------------------------------------- questions
# when: dotted path + list of allowed values. No when = always asked.
# feeds: what changes downstream. Shown to the person. This is the trust rule.

SECTIONS = [
    ("identity", "WHO YOU ARE", [
        {"k": "personal.full_name", "q": "Full legal name?", "feeds": "every document and application", "t": "str"},
        {"k": "personal.phone", "q": "Best phone number?", "feeds": "applications, follow-up, interview scheduling", "t": "str"},
        {"k": "personal.email", "q": "Email an agent can read? (not a private one)", "feeds": "confirmation emails, reply tracking", "t": "str"},
        {"k": "personal.address_line1", "q": "Street address?", "feeds": "applications, commute distance", "t": "str"},
        {"k": "personal.city", "q": "City?", "feeds": "job radius", "t": "str"},
        {"k": "personal.state", "q": "State (2 letters)?", "feeds": "job radius, tax forms", "t": "str"},
        {"k": "personal.zip", "q": "ZIP?", "feeds": "job radius, local programs", "t": "str"},
    ]),

    ("money_in", "MONEY IN - asked first, it is why you came", [
        {"k": "situation.status", "q": "Right now you are...",
         "choices": ["unemployed", "employed", "self_employed", "retired", "disabled"],
         "feeds": "which layers run at all", "t": "choice"},

        # --- unemployed branch
        {"k": "situation.target_jobs", "q": "What kinds of work do you want? (comma separated)",
         "when": [("situation.status", ["unemployed"])],
         "feeds": "the four buckets, the searches run", "t": "list"},
        {"k": "situation.wont_do", "q": "What will you absolutely not do?",
         "when": [("situation.status", ["unemployed"])],
         "feeds": "excludes - keeps bad matches out of the twelve", "t": "list"},
        {"k": "situation.travel_miles", "q": "How far will you travel for work? (miles)",
         "when": [("situation.status", ["unemployed"])],
         "feeds": "the radius on every search", "t": "int"},
        {"k": "situation.pay_floor", "q": "What yearly pay makes it worth it? (just the number)",
         "when": [("situation.status", ["unemployed"])],
         "feeds": "the pay filter - nothing below this gets applied to", "t": "int"},

        # --- employed branch
        {"k": "situation.current_role", "q": "What do you do now?",
         "when": [("situation.status", ["employed", "self_employed"])],
         "feeds": "the resume, and what counts as a step up", "t": "str"},
        {"k": "situation.would_leave_for", "q": "What would make you leave?",
         "when": [("situation.status", ["employed"])],
         "feeds": "low-volume pipeline stays warm instead of running hard", "t": "str"},

        # --- retired branch
        {"k": "situation.retired_note", "q": "Anything you still want to earn from, or fully done?",
         "when": [("situation.status", ["retired"])],
         "feeds": "no resume is built unless you name something", "t": "str"},
    ]),

    ("what_you_have", "WHAT YOU HAVE", [
        {"k": "inventory.tools", "q": "What tools do you own? (comma separated)",
         "feeds": "which weekend projects are buildable today", "t": "list"},
        {"k": "inventory.budget", "q": "What is a normal amount to spend on a project? (dollars)",
         "feeds": "every project is priced against this", "t": "int"},
        {"k": "assets.vehicle", "q": "What kind of car, and does it run?",
         "feeds": "commute radius - a car that does not run changes every search", "t": "str"},
        {"k": "assets.space", "q": "Do you have a garage, yard, or workspace?",
         "feeds": "which projects are possible at all", "t": "str"},
        {"k": "assets.hidden_skills", "q": "Anything you are good at that never made it onto a resume?",
         "feeds": "hobbies that can pay, and one more job bucket", "t": "list"},
    ]),

    ("household", "WHO YOU FEED", [
        {"k": "household.adults", "q": "How many adults in the house?",
         "feeds": "meal quantities and grocery cost", "t": "int"},
        {"k": "household.children", "q": "How many children, and what ages? (e.g. 2 kids, 8 and 11)",
         "feeds": "meal quantities, kid activities, school-year scheduling", "t": "str"},
        {"k": "household.kids_interests", "q": "What are the kids into?",
         "when": [("household.children", ["*nonempty"])],
         "feeds": "cheap activities and gifts that do not wreck the budget", "t": "list"},
    ]),

    ("health", "HEALTH AND WELLNESS", [
        {"k": "health.conditions", "q": "Any health conditions the meals should respect?",
         "feeds": "meal planning - and it will ask what your doctor said next", "t": "list"},
        {"k": "health.doctor_rules", "q": "What did your doctor tell you to limit or avoid? (their words, not yours)",
         "when": [("health.conditions", ["*nonempty"])],
         "feeds": "HARD CONSTRAINTS. The system never invents these - it only follows them", "t": "str"},
        {"k": "health.allergies", "q": "Any allergies? (these are hard stops, nothing overrides them)",
         "feeds": "every grocery list and every recipe, permanently", "t": "list"},
        {"k": "health.meal_goal", "q": "What would you like meals to do for you?",
         "feeds": "meal plans, prep schedule, weekly grocery cost", "t": "str"},
        {"k": "health.weekly_food_budget", "q": "What do you spend on food in a week? (dollars)",
         "feeds": "whether the meal plan is realistic", "t": "int"},
    ]),

    ("spending", "MONEY OUT - asked last, it is the sensitive one", [
        {"k": "spending.recurring_costs", "q": "What do you pay for every month that you would like to cut?",
         "feeds": "savings suggestions - finds the subscriptions you forgot", "t": "list"},
        {"k": "spending.buy_regularly", "q": "What do you buy over and over?",
         "feeds": "shopping watch - flags when it is cheaper", "t": "list"},
        {"k": "spending.wardrobe_interest", "q": "Want outfit suggestions? You send a photo, it shows you looks on you.",
         "choices": ["yes", "no", "maybe later"], "feeds": "the wardrobe layer", "t": "choice"},
        {"k": "spending.wardrobe_budget", "q": "If yes - what is a fair amount for a few outfits? (dollars)",
         "when": [("spending.wardrobe_interest", ["yes", "maybe later"])],
         "feeds": "which stores get suggested first - cheap first, always", "t": "int"},
    ]),

    ("wellbeing", "WHAT KEEPS YOU WELL", [
        {"k": "wellbeing.hobbies_pay", "q": "Any hobbies that could make money?",
         "feeds": "the earn-from-home projects", "t": "list"},
        {"k": "wellbeing.hobbies_relax", "q": "Any hobbies that just make you feel better?",
         "feeds": "the stress-relief projects - a different list from the money ones", "t": "list"},
        {"k": "wellbeing.bored_behavior", "q": "When you are bored and have money, what usually happens?",
         "feeds": "the spend-window nudge - it catches that moment on purpose", "t": "str"},
        {"k": "wellbeing.idle_days", "q": "How many quiet days before it should nudge you? (default 5)",
         "feeds": "idleness detection - it speaks up instead of waiting to be used", "t": "int"},
    ]),
]


# ----------------------------------------------------------------- state
def load_state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    return {"answers": {}, "done": [], "started": date.today().isoformat()}


def save_state(st):
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(st, fh, indent=2)


def get_path(d, dotted):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(d, dotted, value):
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def condition_met(when, answers):
    for path, allowed in when:
        val = get_path(answers, path)
        if "*nonempty" in allowed:
            empty = val in (None, "", [], 0)
            if empty:
                return False
            continue
        if val not in allowed:
            return False
    return True


def coerce(q, raw):
    t = q["t"]
    raw = raw.strip()
    if t == "int":
        try:
            return int("".join(c for c in raw if c.isdigit()) or 0)
        except ValueError:
            return 0
    if t == "list":
        return [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if t == "choice":
        low = raw.lower().replace("-", "_").replace(" ", "_")
        return low if low in q["choices"] else q["choices"][0]
    return raw


# ----------------------------------------------------------------- asking
def ask(q, answers, num, total):
    cur = get_path(answers, q["k"])
    print("\n" + "-" * 64)
    print("  [%d/%d] %s" % (num, total, q["q"]))
    print("  -> feeds: %s" % q["feeds"])
    if "choices" in q:
        print("  choices: %s" % " / ".join(q["choices"]))
    if cur not in (None, "", []):
        print("  (saved: %s - press Enter to keep)" % cur)
    sys.stdout.write("  > ")
    sys.stdout.flush()
    raw = sys.stdin.readline()
    if raw == "":
        raise EOFError
    if raw.strip() == "" and cur not in (None, "", []):
        return cur
    return coerce(q, raw)


def run():
    st = load_state()
    answers = st["answers"]

    flat = [(s, q) for s, _, qs in SECTIONS for q in qs]
    total = len(flat)

    print("=" * 64)
    print("  COMMON AI - setup")
    print("=" * 64)
    print("  Every question shows what it changes. If one does not make sense,")
    print("  press Enter to skip - nothing breaks.")
    print("  Quit any time with Ctrl-C and come back where you left off.")

    n = 0
    try:
        for sec_id, sec_title, qs in SECTIONS:
            live = [q for q in qs if "when" not in q or condition_met(q["when"], answers)]
            if not live:
                if sec_id not in st["done"]:
                    st["done"].append(sec_id)
                continue
            print("\n\n### %s ###" % sec_title)
            for q in qs:
                if "when" in q and not condition_met(q["when"], answers):
                    continue
                n += 1
                val = ask(q, answers, n, total)
                set_path(answers, q["k"], val)
                save_state(st)
            if sec_id not in st["done"]:
                st["done"].append(sec_id)
            save_state(st)
    except (KeyboardInterrupt, EOFError):
        save_state(st)
        print("\n\nSaved. %d of %d answered. Run again to resume." % (n, total))
        return 0

    st["completed"] = date.today().isoformat()
    save_state(st)
    print("\n" + "=" * 64)
    print("  Done. All %d answered." % n)
    write_profile(answers)
    return 0


# ----------------------------------------------------------------- output
def write_profile(answers):
    """Merge the intake into profile.json without destroying what is already there."""
    base = {}
    if os.path.exists(PROFILE):
        with open(PROFILE, encoding="utf-8") as fh:
            base = json.load(fh)

    for k, v in answers.items():
        base[k] = v

    base["_intake"] = {
        "completed": date.today().isoformat(),
        "note": "Written by intake.py. Employment history and buckets are edited directly.",
    }
    base.setdefault("rules", {}).setdefault("min_tenure_days_for_resume", 90)

    # no resume is built for someone who is retired with nothing to earn from
    sit = base.get("situation", {})
    if sit.get("status") == "retired" and not sit.get("retired_note"):
        base.setdefault("rules", {})["skip_resume"] = True

    with open(PROFILE, "w", encoding="utf-8") as fh:
        json.dump(base, fh, indent=2, ensure_ascii=False)
    print("  Wrote %s" % PROFILE)
    return base


def status():
    st = load_state()
    print("Sections completed: %s" % (", ".join(st["done"]) or "none"))
    print("Answers so far: %d" % len(st["answers"]))
    for sec_id, sec_title, _ in SECTIONS:
        print("  %s %s" % ("[x]" if sec_id in st["done"] else "[ ]", sec_title))
    return 0


def render():
    st = load_state()
    write_profile(st["answers"])
    return 0


def reset():
    if os.path.exists(STATE):
        os.rename(STATE, STATE + ".bak")
        print("Moved old answers to %s.bak" % STATE)
    return 0


def main(argv):
    if "--status" in argv:
        return status()
    if "--render" in argv:
        return render()
    if "--reset" in argv:
        return reset()
    return run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
