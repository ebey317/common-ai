#!/usr/bin/env python3
"""
COMMON AI - import the Applications Log into ledger.csv
======================================================
The log is prose. The ledger is state. This bridges them once.

  python3 import_log.py --dry-run   # show the table, write nothing
  python3 import_log.py             # write ledger.csv

SOURCE OF TRUTH: "Your Name - Applications Log" (Google Doc
1Dp1IPUSXoY7mXM1FNTMtpfNZdGH_YxRqvs3bYaj6Bpc), read 2026-11-23.

RULES APPLIED
- Only SUBMITTED applications are imported. Held, blocked, not-submitted, and
  "forgot to send" items are excluded - the log lists them separately and
  counting them would inflate the pipeline.
- Bucket assignment follows the log's own cadence definition: AI = dream,
  commercial HVAC = trade, industrial maintenance = adjacent,
  warehouse/general labor = floor.
- Status maps to the ledger's vocabulary. An interview invite is NOT "applied" -
  it is progress, and progress stops the aging clock.
- The total is verified against the log's stated count (36 as of 2026-11-22).
  A mismatch fails the import rather than writing a wrong ledger.
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.csv")
FIELDS = ["id", "bucket", "company", "role", "url", "applied", "status", "last_check", "notes"]

# (applied, bucket, company, role, status, note)
# status: applied | interview | rejected
ENTRIES = [
    # ---- 2026-11-18 : 10 skilled-lane submissions
    ("2026-11-18", "adjacent", "Example Employer", "Industrial Maintenance Technician", "interview",
     "Karen Ellery interview invite Nov 20; call 763-957-5100 or reply Mon"),
    ("2026-11-18", "trade", "Example Employer", "HVAC Technician", "applied",
     "V2X/Vertex seat, $38.51/hr W2; RTR agreement is the owner's step"),
    ("2026-11-18", "trade", "Example Employer", "HVAC and Refrigeration Service Technician", "rejected",
     "Declined Nov 20 by Dylan Holok - experience does not match"),
    ("2026-11-18", "adjacent", "Example Employer", "Maintenance Technician", "applied",
     "Avon IN, $30-37/hr, multiple shifts"),
    ("2026-11-18", "adjacent", "Example Employer", "Maintenance Technician", "applied",
     "Direct hire, 1st shift 7-3:30"),
    ("2026-11-18", "adjacent", "Example Employer", "Maintenance Technician", "applied",
     "$41.98/hr; automated screening questions arrived Nov 21-22"),
    ("2026-11-18", "adjacent", "Example Employer", "Maintenance Technician (Brownsburg)", "applied",
     "$75-88K/yr, industrial via staffing"),
    ("2026-11-18", "adjacent", "Example Employer", "Maintenance Mechanic II", "applied",
     "$32-42/hr, 1st shift 6:30-2:30"),
    ("2026-11-18", "adjacent", "Example Employer", "Maintenance Technician (Plainfield)", "applied",
     "$26-32/hr, Mon-Fri 8-5"),
    ("2026-11-18", "trade", "Example Employer", "Install Apprentice", "applied",
     "$20-25/hr, install apprentice under a lead"),

    # ---- 2026-11-19 : 7 entry-level lane
    ("2026-11-19", "floor", "Example Employer", "Warehouse Associate", "applied",
     "$15.25-18.25/hr, Mon-Fri 7:30-4:30"),
    ("2026-11-19", "floor", "Example Employer", "Warehouse / Fulfillment Associate", "interview",
     "Invited to office Nov 19; 4652 W 38th St, (317) 315-5840; needs pass"),
    ("2026-11-19", "floor", "Example Employer", "Production Associate", "applied",
     "$16-18/hr, 6am start"),
    ("2026-11-19", "floor", "Example Employer", "Production Associate", "applied",
     "$21.23/hr, nights 10:30pm-7am Sun-Thu"),
    ("2026-11-19", "floor", "Example Employer", "Woodworking Production Associate", "applied",
     "$17-22/hr, training provided"),
    ("2026-11-19", "floor", "Example Employer", "Production Associate II", "applied",
     "Greenfield IN, $18-20/hr, day shift"),
    ("2026-11-19", "floor", "Example Employer", "Warehouse General Laborer", "applied",
     "$18-19/hr, entry level"),

    # ---- 2026-11-19 : 10 refined lanes
    ("2026-11-19", "floor", "Example Employer", "Crew Member", "interview",
     "INTERVIEW Wed Nov 25 offered; 3640 S Keystone; needs time pick + pass"),
    ("2026-11-19", "floor", "Example Employer", "3rd Shift Team Member", "interview",
     "Availability sent Nov 19 09:15; awaiting their time; 2525 N High School Rd"),
    ("2026-11-19", "floor", "Example Employer", "Day Shift Team Member", "applied",
     "$11.50-15/hr, moved to Review Nov 19"),
    ("2026-11-19", "floor", "Example Employer", "Team Member (South Emerson)", "rejected",
     "Interview CANCELLED by employer Nov 21"),
    ("2026-11-19", "trade", "Example Employer", "Commercial HVAC/R Service Technician", "applied",
     "Westfield IN, $35-50/hr; resume acknowledged in AOL Nov 19"),
    ("2026-11-19", "trade", "NCW", "HVAC/Refrigeration Installer", "applied",
     "$35-40/hr contract, commercial"),
    ("2026-11-19", "trade", "Example Employer", "HVAC Technician", "applied",
     "$25-45/hr, commercial rooftop/AHU/VAV"),
    ("2026-11-19", "adjacent", "Example Employer", "Hotel Maintenance Technician II", "applied",
     "$17/hr part-time"),
    ("2026-11-19", "adjacent", "Example Employer", "Maintenance Technician (Holiday Inn Express)", "applied",
     "$18-26/hr + $1,000 bonus; survey status disputed - confirm with the owner"),
    ("2026-11-19", "adjacent", "Example Employer", "Maintenance Technician - Commercial", "applied",
     "$20-35/hr; Application #53440598 received"),

    # ---- 2026-11-19 evening
    ("2026-11-19", "adjacent", "Example Employer", "Maintenance Technician Nights", "rejected",
     "Submitted under Option B ruling; declined Nov 20 via ADP"),

    # ---- 2026-11-20 : evening batch of 7
    ("2026-11-20", "adjacent", "Example Employer", "Industrial Maintenance Technician", "applied",
     "Lebanon IN, $25-32/hr, multiple shifts"),
    ("2026-11-20", "adjacent", "Example Employer", "Industrial Maintenance Technician", "applied",
     "Lebanon IN, $25-35/hr, 2nd shift"),
    ("2026-11-20", "adjacent", "Example Employer", "Industrial Maintenance Technician", "applied",
     "Lebanon IN, $26-34/hr"),
    ("2026-11-20", "trade", "Example Employer", "Commercial Refrigeration Service Technician", "applied",
     "$30-38/hr, full-time, no on-call"),
    ("2026-11-20", "floor", "Example Employer", "Warehouse Associate", "applied",
     "$15.25-18.25/hr, no experience required"),
    ("2026-11-20", "floor", "Example Employer", "General Labor Associate", "applied",
     "Whitestown IN, $16.50/hr 2nd shift"),
    ("2026-11-20", "floor", "Example Employer", "General Labor", "applied",
     "Beech Grove IN, $18-20/hr"),

    # ---- 2026-11-22
    ("2026-11-22", "trade", "Example Employer", "HVAC Installer / Service Technician", "applied",
     "Whiteland IN, $25-60/hr listed; applied by direct email with resume"),
]

# What the log says the total should be, as of the read date.
EXPECTED_TOTAL = 36

# Deliberately NOT imported - logged so nothing gets counted twice later.
EXCLUDED = [
    ("Mitsubishi Turbocharger", "held - felony-detail free text is the owner's hands"),
    ("Heartland FPG", "hard stop - felony explanation required in screening"),
    ("Mayer Fabrics", "hard stop - background-check consent"),
    ("Summers Plumbing Heating & Cooling", "left at the owner's word Nov 19"),
    ("Godby Heating Plumbing Electric", "left at the owner's word Nov 19"),
    ("Verus Engineering", "form failed, email drafted but NOT sent"),
    ("OpenTrain", "terms box waiting on the owner"),
    ("Carlisle / Job&Talent", "filled in, the owner said no"),
    ("AfterQuery / Alpheva / Sephora / GEMCO", "blocked or dropped"),
    ("Fast-food batch of 6 (Nov 21)", "not started - links handed to the owner"),
]


def build():
    rows = []
    for i, (applied, bucket, company, role, status, note) in enumerate(ENTRIES, 1):
        rows.append({
            "id": "A%04d" % i,
            "bucket": bucket,
            "company": company,
            "role": role,
            "url": "",
            "applied": applied,
            "status": status,
            "last_check": "",
            "notes": note,
        })
    return rows


def main(argv):
    dry = "--dry-run" in argv
    rows = build()

    print("=" * 74)
    print("  IMPORT - Applications Log -> ledger.csv")
    print("=" * 74)

    counts = {}
    for r in rows:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    st = {}
    for r in rows:
        st[r["status"]] = st.get(r["status"], 0) + 1

    print("\n  total entries : %d   (log says %d)" % (len(rows), EXPECTED_TOTAL))
    bucket_keys = ("dream", "trade", "adjacent", "floor")
    print("  by bucket     : "
          + "  ".join("%s=%d" % (k, counts.get(k, 0)) for k in bucket_keys))
    print("  by status     : " + "  ".join("%s=%d" % (k, st[k]) for k in sorted(st)))
    print("\n  excluded on purpose (%d):" % len(EXCLUDED))
    for name, why in EXCLUDED:
        print("    - %-38s %s" % (name, why))

    if len(rows) != EXPECTED_TOTAL:
        print("\n  MISMATCH: %d entries built but the log states %d." % (len(rows), EXPECTED_TOTAL))
        print("  Not writing. Fix the table first.")
        return 1

    if counts.get("dream", 0) == 0:
        print("\n  NOTE: dream bucket is empty. The log explains why -")
        print("        'AI jobs 0 submitted, all were expert/degree-gated'.")

    print("\n  first 5:")
    for r in rows[:5]:
        print("    %-9s %-9s %-28s %s" % (r["applied"], r["bucket"], r["company"][:28], r["role"][:34]))
    print("  last 5:")
    for r in rows[-5:]:
        print("    %-9s %-9s %-28s %s" % (r["applied"], r["bucket"], r["company"][:28], r["role"][:34]))

    if dry:
        print("\n  DRY RUN - ledger.csv untouched.")
        return 0

    backup = LEDGER + ".bak"
    if os.path.exists(LEDGER):
        os.replace(LEDGER, backup)
        print("\n  previous ledger saved to ledger.csv.bak")

    with open(LEDGER, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print("  wrote %d rows to ledger.csv" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
