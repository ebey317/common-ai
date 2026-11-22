#!/usr/bin/env python3
"""
Common Use AI - Job Ledger
--------------------------
Twelve applications a month. Three a week. Four buckets, round-robin.
Each application lives 90 days, gets checked, then expires at 180.
The clock never stops, even when you're hired.

  python3 ledger.py add <bucket> "<company>" "<role>" [url]
  python3 ledger.py age                    # advance lifecycle, no writes to apps
  python3 ledger.py report                 # the weekly receipt
  python3 ledger.py rotation               # what to apply to this week
  python3 ledger.py seed                   # sample data to look at

Storage: ledger.csv beside this file.
"""

import csv
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.csv")

BUCKETS = {
    "dream":    "Reach - the job you'd take in a heartbeat",
    "trade":    "Trade - what you're already paid to do",
    "adjacent": "Adjacent - your other real credential",
    "floor":    "Floor - money this week, no waiting",
}
ORDER = ["dream", "trade", "adjacent", "floor"]

CHECK_DAYS = 90
EXPIRE_DAYS = 180
PER_MONTH = 12
PER_WEEK = 3

FIELDS = ["id", "bucket", "company", "role", "url", "applied", "status", "last_check", "notes"]

ALIVE = {"applied", "aged"}
CLOSED = {"replied", "interview", "hired", "rejected", "expired", "withdrawn"}


# ---------------------------------------------------------------- storage
def load():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def save(rows):
    with open(LEDGER, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def next_id(rows):
    return "A%04d" % (len(rows) + 1)


# ---------------------------------------------------------------- lifecycle
def days_since(applied, today):
    return (today - date.fromisoformat(applied)).days


def lifecycle(row, today):
    """Return (status, days_old, days_to_check, days_to_expire, note)."""
    if row["status"] in CLOSED:
        d = days_since(row["applied"], today)
        return row["status"], d, None, None, "closed"

    age = days_since(row["applied"], today)
    to_check = CHECK_DAYS - age
    to_expire = EXPIRE_DAYS - age

    if age >= EXPIRE_DAYS:
        return "expired", age, 0, 0, "six months old - the posting is dead, replace it"
    if age >= CHECK_DAYS:
        return "aged", age, 0, to_expire, "checked once, still live until day %d" % EXPIRE_DAYS
    return "applied", age, to_check, to_expire, "fresh - check due in %d days" % to_check


# ---------------------------------------------------------------- rotation
def rotation_for(week_of_year):
    """Which three buckets get an application this week. One bucket rests."""
    rest = (week_of_year - 1) % len(ORDER)
    return [b for i, b in enumerate(ORDER) if i != rest], ORDER[rest]


# ---------------------------------------------------------------- commands
def cmd_add(args):
    if len(args) < 3:
        print('usage: ledger.py add <dream|trade|adjacent|floor> "Company" "Role" [url]')
        return 1
    bucket, company, role = args[0].lower(), args[1], args[2]
    url = args[3] if len(args) > 3 else ""
    if bucket not in BUCKETS:
        print("unknown bucket %r - pick one of: %s" % (bucket, ", ".join(ORDER)))
        return 1
    rows = load()
    rows.append({
        "id": next_id(rows), "bucket": bucket, "company": company, "role": role,
        "url": url, "applied": date.today().isoformat(), "status": "applied",
        "last_check": "", "notes": "",
    })
    save(rows)
    print("logged %s  %-9s %s - %s" % (rows[-1]["id"], bucket, company, role))
    return 0


def cmd_age(args):
    """Write the lifecycle back into the file so the Sheet always shows truth."""
    rows, today = load(), date.today()
    moved = 0
    for r in rows:
        status, _, _, _, _ = lifecycle(r, today)
        if status != r["status"]:
            print("  %s  %s -> %s   (%s - %s)" % (r["id"], r["status"], status, r["company"], r["role"]))
            r["status"] = status
            if status in ("aged", "expired"):
                r["last_check"] = today.isoformat()
            moved += 1
    save(rows)
    print("\n%d application(s) changed state." % moved)
    return 0


def cmd_report(args):
    rows, today = load(), date.today()
    if not rows:
        print("Ledger is empty. `ledger.py seed` to see what one looks like.")
        return 0

    print("=" * 66)
    print("  YOUR JOB SEARCH - %s" % today.strftime("%A, %B %d, %Y"))
    print("=" * 66)

    live = [r for r in rows if lifecycle(r, today)[0] in ALIVE]
    closed = [r for r in rows if r["status"] in CLOSED]
    replies = [r for r in rows if r["status"] in ("replied", "interview", "hired")]

    print("\n  %d live   %d closed   %d heard back\n" % (len(live), len(closed), len(replies)))

    for b in ORDER:
        mine = [r for r in rows if r["bucket"] == b]
        liveb = [r for r in mine if lifecycle(r, today)[0] in ALIVE]
        print("  %s  (%s)" % (b.upper(), BUCKETS[b]))
        print("    %d live, %d total" % (len(liveb), len(mine)))
        if not liveb:
            print("    -- nothing live in this bucket. that's a hole.")
        for r in liveb:
            status, age, to_check, to_expire, note = lifecycle(r, today)
            flag = "  <-- CHECK NOW" if to_check == 0 and status != "expired" else ""
            print("    %s %-22s %-26s %3dd  %s%s" % (r["id"], r["company"][:22], r["role"][:26],
                                                     age, status, flag))
        print()

    need = [r for r in live if lifecycle(r, today)[0] == "aged"]
    dead = [r for r in rows if lifecycle(r, today)[0] == "expired"]
    if need:
        print("  NEEDS A 90-DAY CHECK (%d):" % len(need))
        for r in need:
            print("    %s  %s - %s" % (r["id"], r["company"], r["role"]))
        print()
    if dead:
        print("  EXPIRED - REPLACE THESE (%d):" % len(dead))
        for r in dead:
            print("    %s  %s - %s" % (r["id"], r["company"], r["role"]))
        print()

    print("-" * 66)
    print("  Every application is checked at 90 days and replaced at 180.")
    print("  Nothing here needs your attention unless it says CHECK NOW.")
    print("-" * 66)
    return 0


def cmd_rotation(args):
    today = date.today()
    wk = today.isocalendar()[1]
    active, rest = rotation_for(wk)
    print("=" * 66)
    print("  THIS WEEK'S THREE - week %d" % wk)
    print("=" * 66)
    print("\n  Apply to one in each of these:\n")
    for b in active:
        print("    %-9s %s" % (b.upper(), BUCKETS[b]))
    print("\n  Resting this week: %s" % rest.upper())
    print("\n  Three, not twelve. Twelve comes from four weeks of three.\n")
    return 0


def cmd_seed(args):
    today = date.today()
    sample = [
        ("dream", "Anthropic", "Solutions Engineer", 12),
        ("dream", "Nous Research", "Agent Runtime Engineer", 45),
        ("dream", "Scale AI", "AI Operations Lead", 95),
        ("trade", "Johnson Controls", "Commercial HVAC Tech", 8),
        ("trade", "Trane", "Service Technician", 41),
        ("trade", "Carrier", "Commercial Installer", 120),
        ("adjacent", "Example Former Employer C", "Facility Maintenance", 6),
        ("adjacent", "Allison Transmission", "Industrial Maintenance", 60),
        ("adjacent", "Eli Lilly", "Maintenance Mechanic", 200),
        ("floor", "Amazon", "Warehouse Associate", 3),
        ("floor", "FedEx Ground", "Package Handler", 30),
        ("floor", "Example Employer", "Temp - General Labor", 100),
    ]
    rows = []
    for i, (bucket, company, role, ago) in enumerate(sample, 1):
        applied = today - timedelta(days=ago)
        rows.append({
            "id": "A%04d" % i, "bucket": bucket, "company": company, "role": role,
            "url": "", "applied": applied.isoformat(),
            "status": "replied" if company == "Trane" else "applied",
            "last_check": "", "notes": "",
        })
    save(rows)
    print("seeded %d sample applications across 4 buckets" % len(rows))
    return 0


COMMANDS = {"add": cmd_add, "age": cmd_age, "report": cmd_report,
            "rotation": cmd_rotation, "seed": cmd_seed}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 0 if len(argv) < 2 else 1
    return COMMANDS[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
