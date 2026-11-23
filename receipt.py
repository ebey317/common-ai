#!/usr/bin/env python3
"""
COMMON AI - the 30-day receipt
==============================
"Does this earn its keep?" answered with arithmetic instead of adjectives.

  python3 receipt.py                  # the 30-day breakdown, on screen
  python3 receipt.py --video          # the same thing as a narrated MP4
  python3 receipt.py --fee 20         # what you pay per month

The rule this file exists to enforce: it reports what was FOUND and, separately,
what was COLLECTED. Those are never merged. A receipt that claims earnings the
system did not cause is the same confident lying every other tool does, and it
would destroy the only thing that makes the rest believable.

Worth is stated against real comparables, not against other software:
one grant pays the fee for years; a rent drop is measured in per-year dollars.
"""

import csv
import json
import os
import sys
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "ledger.csv")
OPPS = os.path.join(HERE, "opportunities.json")
PROFILE = os.path.join(HERE, "profile.json")

WINDOW_DAYS = 30


def _json(p, d):
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return d


def within(d, days):
    try:
        return (date.today() - date.fromisoformat(str(d)[:10])).days <= days
    except Exception:
        return False


def breakdown(fee):
    rows = []
    if os.path.exists(LEDGER):
        with open(LEDGER, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))

    recent = [r for r in rows if within(r.get("applied"), WINDOW_DAYS)]
    interviews = [r for r in rows if r.get("status") == "interview"]
    live = [r for r in rows if r.get("status") in ("applied", "aged")]

    proof = ("received", "invite", "interview", "declined", "cancel",
             "application #", "offer")
    verified = [r for r in rows
                if any(p in (r.get("notes") or "").lower() for p in proof)]

    opps = _json(OPPS, {})
    grants = opps.get("opportunities", [])
    open_grants = [g for g in grants if g.get("status") == "open"]
    entered = [g for g in grants if g.get("status") == "entered"]
    grant_value = sum(int(g.get("amount") or 0) for g in open_grants)

    prof = _json(PROFILE, {})
    costs = prof.get("spending", {}).get("recurring_costs", [])
    monthly_cost = sum(int(c.get("amount_monthly") or 0) for c in costs)
    # Household cost is identical in both scenarios, so it cancels: the real
    # delta is the RENT line minus the lot-rent ceiling. Comparing total spend
    # against lot rent alone would overstate the drop by the household figure -
    # an inflated number in a receipt whose whole job is not inflating.
    lot_ceiling = 600
    rent_line = sum(int(c.get("amount_monthly") or 0) for c in costs
                    if "rent" in str(c.get("label", "")).lower()
                    and "lot" not in str(c.get("label", "")).lower())
    rent_drop = max(0, rent_line - lot_ceiling) if rent_line else 0

    annual_fee = fee * 12
    return {
        "fee": fee,
        "annual_fee": annual_fee,
        "recent": len(recent),
        "live": len(live),
        "total": len(rows),
        "verified": len(verified),
        "interviews": [r.get("company") for r in interviews],
        "open_grants": len(open_grants),
        "entered_grants": len(entered),
        "grant_value": grant_value,
        "monthly_cost": monthly_cost,
        "rent_drop": rent_drop,
        "rent_drop_year": rent_drop * 12,
    }


def report(f):
    out = []
    a = out.append
    a("=" * 68)
    a("  YOUR LAST 30 DAYS")
    a("  what it found, what you did, what it cost")
    a("=" * 68)

    a("\n  FOUND")
    a("    %d live interviews: %s" % (
        len(f["interviews"]), ", ".join(str(x) for x in f["interviews"][:4]) or "none"))
    a("    %d applications tracked, %d with a real employer reply"
      % (f["total"], f["verified"]))
    a("    %d open grants worth up to $%s" % (f["open_grants"], format(f["grant_value"], ",")))
    if f["rent_drop"]:
        a("    a cheaper living path: $%d/mo = $%s/yr"
          % (f["rent_drop"], format(f["rent_drop_year"], ",")))

    a("\n  YOU DID")
    a("    %d applications in the last 30 days" % f["recent"])
    a("    %d still live in the pipeline" % f["live"])

    a("\n  WHAT IT COST")
    a("    $%d/month  =  $%s/year" % (f["fee"], format(f["annual_fee"], ",")))

    a("\n  WHAT THAT FEE IS WORTH")
    if f["grant_value"]:
        a("    one open grant ($%s) covers %d years of the fee"
          % (format(f["grant_value"], ","),
             int(f["grant_value"] / f["annual_fee"]) if f["annual_fee"] else 0))
    if f["rent_drop_year"]:
        a("    the rent drop is %dx the annual fee, every year"
          % int(f["rent_drop_year"] / f["annual_fee"]))
    if f["interviews"]:
        a("    one interview that lands makes the fee irrelevant")

    a("\n  " + "-" * 64)
    a("  identified: $%s   |   collected: $0" %
      format(f["grant_value"] + f["rent_drop_year"], ","))
    a("  Found is not earned. The system surfaces it; you act on it.")
    a("  This line stays honest or the whole receipt is worthless.")
    return "\n".join(out)


def main(argv):
    fee = 20
    if "--fee" in argv:
        try:
            fee = int(argv[argv.index("--fee") + 1])
        except Exception:
            pass

    f = breakdown(fee)
    print(report(f))

    if "--video" in argv:
        sys.path.insert(0, HERE)
        import weekly_video as wv

        rows = list(csv.DictReader(open(LEDGER, encoding="utf-8"))) if os.path.exists(LEDGER) else []
        iv = [r for r in rows if r.get("status") == "interview"]
        rej = [r for r in rows if r.get("status") == "rejected"]
        opps = _json(OPPS, {}).get("opportunities", [])

        sc = []
        sc.append(("30 DAYS", "THE FULL BREAKDOWN",
                   "what it found, what you did, what it cost",
                   "Thirty days. Let's go through all of it, honestly. What the "
                   "system found, what you did with it, and exactly what it costs. "
                   "Nothing in here is rounded up to look better."))

        sc.append(("THE HEADLINE", "%d APPLICATIONS" % f["total"],
                   "%d still live" % f["live"],
                   "%d applications tracked in the pipeline. %d of them are still "
                   "live and could still turn into something. The rest have already "
                   "resolved one way or another." % (f["total"], f["live"])))

        sc.append(("THE REAL TEST", "%d OF %d VERIFIED" % (f["verified"], f["total"]),
                   "an employer wrote back",
                   "Now the number most systems hide. %d of %d have an actual reply "
                   "from an employer. The other %d are on your word alone. That gap "
                   "is the difference between a pipeline and a wish list."
                   % (f["verified"], f["total"], f["total"] - f["verified"])))

        for i, r in enumerate(iv[:4], 1):
            sc.append(("INTERVIEW %d OF %d" % (i, len(iv)),
                       str(r.get("company", "?")).upper()[:28],
                       str(r.get("role", ""))[:44],
                       "Interview %d. %s, for the %s position. %s"
                       % (i, r.get("company"), r.get("role"),
                          (r.get("notes") or "no details recorded").split(";")[0])))

        sc.append(("WHAT DIDN'T WORK", "%d CLOSED OUT" % len(rej),
                   "learned, not lost",
                   "%d closed out. Caplinger said the experience did not match. "
                   "Steak and Shake cancelled. CraftMark declined. Those are answers, "
                   "not failures - each one frees a slot for something better." % len(rej)))

        sc.append(("THE MONEY SIDE", "GRANTS",
                   "%d open worth $%s" % (f["open_grants"], format(f["grant_value"], ",")),
                   "On the money side: %d grant open worth up to %s dollars, and %d "
                   "already entered. The open one is the fastest real money on this "
                   "board and it has not been filed yet."
                   % (f["open_grants"], format(f["grant_value"], ","), f["entered_grants"])))

        sc.append(("CHEAPER LIVING", "$%d A MONTH" % f["rent_drop"],
                   "$%s a year, identified" % format(f["rent_drop_year"], ","),
                   "Here is the biggest number in this whole receipt. Moving from a "
                   "twelve hundred dollar rent to a six hundred dollar lot rent saves "
                   "%d dollars a month. That is %s dollars a year, every year, and it "
                   "requires no new income at all."
                   % (f["rent_drop"], format(f["rent_drop_year"], ","))))

        sc.append(("WHAT IT COST", "$%d A MONTH" % f["fee"],
                   "$%s a year" % format(f["annual_fee"], ","),
                   "What it costs. %d dollars a month, %s dollars a year. Now compare "
                   "that to a single grant, or to one month of that rent difference."
                   % (f["fee"], format(f["annual_fee"], ","))))

        sc.append(("THE COMPARISON", "THE FEE IS SMALL",
                   "one grant covers %d years" % (int(f["grant_value"] / f["annual_fee"]) if f["annual_fee"] else 0),
                   "One grant at %s dollars covers %d years of this fee. The rent "
                   "difference is %d times the annual cost. This is not competing "
                   "with other software. It is competing with one week of your time."
                   % (format(f["grant_value"], ","),
                      int(f["grant_value"] / f["annual_fee"]) if f["annual_fee"] else 0,
                      int(f["rent_drop_year"] / f["annual_fee"]) if f["annual_fee"] else 0)))

        buckets = {}
        for r in rows:
            buckets[r.get("bucket")] = buckets.get(r.get("bucket"), 0) + 1
        sc.append(("THE FOUR BUCKETS", "DREAM IS EMPTY",
                   "trade %d, adjacent %d, floor %d"
                   % (buckets.get("trade", 0), buckets.get("adjacent", 0),
                      buckets.get("floor", 0)),
                   "Four buckets. Trade: %d. Adjacent: %d. Floor: %d. And the dream "
                   "bucket, the six figure AI job, sits at zero. Not because nobody "
                   "tried - sixty listings were reviewed and every one wanted a degree "
                   "or expert level. That is a real wall, and now it is visible instead "
                   "of a number nobody was watching."
                   % (buckets.get("trade", 0), buckets.get("adjacent", 0),
                      buckets.get("floor", 0))))

        sc.append(("NOT DONE YET", "ZERO FILED",
                   "no LLC, no EIN, no grant submitted",
                   "Now what has not happened. Zero grants filed. No LLC. No EIN. The "
                   "corporate side is completely untouched, and that is the door to "
                   "every larger amount of money there is. The applications ran. The "
                   "business paperwork did not."))

        sc.append(("THE TRAILER", "$7,200 A YEAR, WAITING",
                   "blocked on a piece of paper",
                   "The trailer. Seven thousand two hundred dollars a year sitting "
                   "there, blocked on a title that was never transferred. The cousin "
                   "lost the paperwork. That one document is worth more than any grant "
                   "on this list, and it requires no approval from anybody."))

        sc.append(("WHAT IT CANNOT DO", "AND WON'T PRETEND",
                   "meals, retirement, legal filings",
                   "What it cannot do. It has no meal plan, because there is no health "
                   "record to plan inside and guessing about a kidney condition is not "
                   "a feature. It has no retirement picture, because no account has "
                   "been located. And it will not file a legal document - it drafts, "
                   "you sign."))

        sc.append(("THE LAYERS", "FIVE RUNNING, ZERO RETIRED",
                   "level zero of five",
                   "Five layers running: job search, housing, grants, spending watch, "
                   "wellbeing. Zero retired. That is level zero, and level zero is the "
                   "right place to be starting from. Each one turns off when you can "
                   "say out loud that its problem is gone."))

        sc.append(("WHAT IT NEEDS FROM YOU", "TWO NUMBERS",
                   "food, and the date you told the landlord",
                   "Two things would make the next thirty days better than these. What "
                   "you spend on food in a month, so the money picture closes. And the "
                   "date you first told the landlord about that wall, so ninety days "
                   "stops being a guess and becomes a deadline."))

        sc.append(("THE HONEST LINE", "FOUND, NOT EARNED",
                   "$%s identified, $0 collected" % format(
                       f["grant_value"] + f["rent_drop_year"], ","),
                   "And now the line that keeps every other number believable. "
                   "Identified: %s dollars. Collected: zero. Finding is not earning. "
                   "The system surfaces it and you act on it, and it will never blur "
                   "those two words to make a better report."
                   % format(f["grant_value"] + f["rent_drop_year"], ",")))

        sc.append(("WHAT'S NEXT", "THE NEXT 30 DAYS",
                   "one grant, one call, one number",
                   "So what actually matters in the next thirty days. One thing only, "
                   "per area. File the open grant. Call Karen back. And tell the system "
                   "what you spend on food, because it is the last number standing "
                   "between you and a full money picture."))

        sc.append(("COMMON USE AI", "EARNING ITS KEEP",
                   "or you turn it off",
                   "That is the thirty days. It identified %s dollars for %s dollars "
                   "of cost. If it ever stops doing that, you turn the layer off and "
                   "stop paying. That is the deal."
                   % (format(f["grant_value"] + f["rent_drop_year"], ","),
                      format(f["annual_fee"], ","))))

        return wv.render(sc, out=os.path.join(HERE, "receipt_30day.mp4"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
