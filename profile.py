#!/usr/bin/env python3
"""
Common Use AI - Profile Renderer
--------------------------------
One source of truth (profile.json). Either view renders from it.

  python3 profile.py gaps                 # what's missing or unconfirmed
  python3 profile.py tenure               # every job against the 90-day rule
  python3 profile.py resume trade         # HVAC resume - dated jobs only
  python3 profile.py resume tech          # AI resume - projects
  python3 profile.py form                 # full history, for ATS forms

The rule: a job under 90 days never gets a dated entry on a resume.
Its work folds into the hands-on line - real experience, no tenure signal.
Application forms are different: full history, all of it, or you get cut.
"""

import json
import os
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load():
    """Read the profile, or say plainly what to do instead of raising.

    A raw traceback on a clean clone is the first thing a stranger would see,
    and it says nothing about the one command that fixes it.
    """
    if not os.path.exists(PROFILE):
        print("  No profile.json yet.")
        print("  That file is the source of truth every document here renders from.")
        print("  Build it first:   python3 intake.py")
        raise SystemExit(2)
    try:
        with open(PROFILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print("  profile.json exists but could not be read (%s)." % str(exc)[:90])
        print("  Repair it, or start over:   python3 intake.py")
        raise SystemExit(2)


def fmt_date(iso):
    if not iso:
        return "Present"
    y, m, _ = iso.split("-")
    return "%s %s" % (MONTHS[int(m) - 1], y)


def _parse_date(s):
    """Accept YYYY, YYYY-MM or YYYY-MM-DD.

    The intake stores partial dates on purpose - a person often knows the month
    and not the day - and every real profile here uses YYYY-MM. A renderer that
    assumes full ISO dates works only on data nobody has.
    """
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def tenure_days(job):
    a = _parse_date(job.get("start"))
    b = _parse_date(job.get("end")) or date.today()
    if a is None:
        return 0          # an unknown start cannot count toward a threshold
    return (b - a).days


def split_jobs(p):
    keep = p["rules"]["min_tenure_days_for_resume"]
    long_, short = [], []
    for j in p["employment"]:
        (long_ if tenure_days(j) >= keep else short).append(j)
    long_.sort(key=lambda j: str(j.get("start") or ""), reverse=True)
    short.sort(key=lambda j: str(j.get("start") or ""), reverse=True)
    return long_, short


# ---------------------------------------------------------------- commands
def cmd_tenure(args):
    p = load()
    keep = p["rules"]["min_tenure_days_for_resume"]
    print("  %-42s %6s   %s" % ("JOB", "DAYS", "RULE"))
    print("  " + "-" * 64)
    for j in sorted(p["employment"], key=lambda x: x["start"], reverse=True):
        d = tenure_days(j)
        print("  %-42s %6d   %s" % (
            (j["employer"] + " - " + j["title"])[:42], d,
            "KEEP" if d >= keep else "leave off"))
    long_, short = split_jobs(p)
    print("\n  %d on the resume, %d folded into hands-on." % (len(long_), len(short)))
    return 0


def cmd_gaps(args):
    p = load()
    print("=" * 64)
    print("  WHAT'S MISSING")
    print("=" * 64)
    n = 0
    for item in p.get("_needs_confirmation", []):
        n += 1
        print("  %d. %s" % (n, item))
    for j in p["employment"]:
        if not j.get("end_confirmed", True):
            n += 1
            print("  %d. %s end date is a guess (%s)" % (n, j["employer"], j.get("end")))
    per = p["personal"]
    for f, label in (("github", "GitHub"), ("linkedin", "LinkedIn"), ("website", "Website")):
        if not per.get(f):
            n += 1
            print("  %d. %s is blank - it is one of the only free credibility signals" % (n, label))
    if not p["documents"].get("resume_pdf"):
        n += 1
        print("  %d. No resume file on disk. Render one: profile.py resume trade" % n)
    print("\n  %d open item(s)." % n)
    return 0


def _head(p, headline):
    per = p["personal"]
    print(per["full_name"].upper())
    print("%s, %s %s  |  %s  |  %s" % (per["city"], per["state"], per["zip"],
                                       per["phone"], per["email"]))
    print(headline)
    print()


def _hands_on(p, short):
    notes = [j.get("short_stint_note") for j in short if j.get("short_stint_note")]
    if not notes:
        return
    print("HANDS-ON EXPERIENCE")
    for n in notes:
        print("  - %s" % n)
    print("  (Recent short-term work. Listed as experience, not as tenure.)")
    print()


def _staffing(p, short):
    """The contract/staffing block: fills gaps without naming or dating short stints."""
    sp = p.get("staffing_period")
    if sp:
        print("%s - %s" % (sp["label"].upper(), sp["city"]))
        period = fmt_date(sp["start"]) + " - " + (fmt_date(sp["end"]) if sp.get("end") else "Present")
        print("  " + period)
        print("  " + sp["summary"])
        print()
        return
    notes = [j.get("short_stint_note") for j in short if j.get("short_stint_note")]
    if notes:
        print("CONTRACT EXPERIENCE")
        for n in notes:
            print("  - %s" % n)
        print()


def cmd_resume(args):
    if not args or args[0] not in ("trade", "tech"):
        print("usage: profile.py resume <trade|tech>")
        return 1
    dom = args[0]
    p = load()
    d = p["domains"][dom]
    long_, short = split_jobs(p)

    print("=" * 64)
    _head(p, d["headline"])

    print("SUMMARY")
    print("  " + d["summary"])
    print()

    print("SKILLS")
    for s in d["skills"]:
        print("  - %s" % s)
    print()

    if dom == "trade":
        trade_jobs = [j for j in long_ if j.get("domain") == "trade"]
        print("EXPERIENCE")
        for j in trade_jobs:
            print("%s - %s" % (j["title"], j["employer"]))
            print("  %s   |   %s - %s" % (j["city"], fmt_date(j["start"]), fmt_date(j["end"])))
            print("  " + j["summary"])
            print()
        _staffing(p, short)
        print("CERTIFICATIONS")
        for c in d["certs"]:
            print("  - %s" % c)
        print()
        print("EDUCATION")
        for e in d["education"]:
            print("  %s - %s (%s)" % (e["credential"], e["school"], e["year"]))
        print()
    else:
        print("PROJECT EXPERIENCE")
        for pr in d["projects"]:
            print("%s" % pr["name"])
            print("  %s" % pr["period"])
            for pt in pr["points"]:
                print("  - %s" % pt)
            print()
        print("CERTIFICATIONS")
        for c in d["certs"]:
            print("  - %s" % c)
        print()
        print("PORTFOLIO")
        print("  %s" % p["personal"]["github"])
        print()

    print("=" * 64)
    return 0


def cmd_form(args):
    """Full history. No curation. This is what an ATS wants."""
    p = load()
    per = p["personal"]
    print("=" * 64)
    print("  FULL EMPLOYMENT HISTORY  (application forms / background check)")
    print("=" * 64)
    print("  This view is deliberately NOT curated. Every job, every date.")
    print("  Omitting a job here is a disqualifier, not a resume choice.\n")
    print("  %s" % per["full_name"])
    print("  %s, %s %s" % (per["address_line1"], per["city"], per["state"] + " " + per["zip"]))
    print("  %s  |  %s" % (per["phone"], per["email"]))
    print()
    for j in sorted(p["employment"], key=lambda x: x["start"], reverse=True):
        d = tenure_days(j)
        mark = "" if d >= p["rules"]["min_tenure_days_for_resume"] else "   <- short stint"
        print("  %-38s %s - %s%s" % (j["employer"][:38], fmt_date(j["start"]),
                                     fmt_date(j["end"]), mark))
        desc = j.get("summary") or j.get("short_stint_note") or ""
        print("    %s, %s - %s" % (j["title"], j["city"], desc[:80]))
        print()
    print("  %d entries total." % len(p["employment"]))
    print("=" * 64)
    return 0


COMMANDS = {"gaps": cmd_gaps, "tenure": cmd_tenure,
            "resume": cmd_resume, "form": cmd_form}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 0 if len(argv) < 2 else 1
    return COMMANDS[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
