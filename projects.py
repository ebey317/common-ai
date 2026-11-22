#!/usr/bin/env python3
"""
Common Use AI - Weekend Projects (the always-on layer)
------------------------------------------------------
Work is why people show up. This is why they stay.

One project a week, priced, matched to the tools they already own.
No "you might enjoy woodworking." Only: you have a saw and pallets are
free, here is a table for $47.

  python3 projects.py seed              # starter inventory + catalog
  python3 projects.py this              # this weekend's project
  python3 projects.py match [budget]    # rank everything by what you own
  python3 projects.py own <tool> ...    # add tools to your inventory
  python3 projects.py budget <dollars>  # set your ceiling

Storage: inventory.json beside this file.
"""

import json
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
INV = os.path.join(HERE, "inventory.json")

CATALOG = [
    # --- pallet builds -------------------------------------------------
    {"id": "P01", "name": "Pallet coffee table", "cat": "pallet", "cost": 47, "hours": 4,
     "tools": ["saw", "drill", "sander"],
     "why": "Pallets are free behind most shops. Two of them make a 4-foot table."},
    {"id": "P02", "name": "Pallet patio bench", "cat": "pallet", "cost": 55, "hours": 3,
     "tools": ["saw", "drill"],
     "why": "Three pallets, four legs, weather stain. Sits outdoors year-round."},
    {"id": "P03", "name": "Pallet vertical garden", "cat": "pallet", "cost": 62, "hours": 4,
     "tools": ["saw", "drill"],
     "why": "One pallet stood on end, landscape fabric, six planters. Feeds you by July."},
    {"id": "P04", "name": "Pallet shoe rack / mudroom bench", "cat": "pallet", "cost": 38, "hours": 3,
     "tools": ["saw", "drill", "sander"],
     "why": "Stacked pallet slats. Cutting the slats is the only real work."},
    {"id": "P05", "name": "Pallet workbench", "cat": "pallet", "cost": 71, "hours": 5,
     "tools": ["saw", "drill", "sander"],
     "why": "Heavy top from doubled pallets. This is the one you build first."},

    # --- off-grid ------------------------------------------------------
    {"id": "O01", "name": "Rain barrel off a downspout", "cat": "off-grid", "cost": 44, "hours": 3,
     "tools": ["drill", "saw"],
     "why": "Food-grade barrel, a diverter, and a spigot. Free water for the garden."},
    {"id": "O02", "name": "Solar phone charger", "cat": "off-grid", "cost": 88, "hours": 2,
     "tools": ["soldering iron"],
     "why": "20W panel, charge controller, USB outlet. No wiring in the house."},
    {"id": "O03", "name": "Rocket stove from scrap", "cat": "off-grid", "cost": 65, "hours": 5,
     "tools": ["angle grinder", "welder"],
     "why": "Burns twigs, heats a pot in four minutes, costs nothing to run."},
    {"id": "O04", "name": "Off-grid shed lighting", "cat": "off-grid", "cost": 96, "hours": 4,
     "tools": ["drill", "soldering iron"],
     "why": "One panel, one battery, four LED strips. Lights a shed with no trench."},

    # --- workshop / tools ----------------------------------------------
    {"id": "W01", "name": "Pegboard wall over the bench", "cat": "workshop", "cost": 58, "hours": 3,
     "tools": ["drill", "saw"],
     "why": "Stops the daily hunt for the tool you just had in your hand."},
    {"id": "W02", "name": "Rolling tool cart from pallets", "cat": "workshop", "cost": 89, "hours": 6,
     "tools": ["saw", "drill", "sander"],
     "why": "Castors, doubled pallet frame, done. Follows you around the job."},
    {"id": "W03", "name": "Scrap-wood clamp rack", "cat": "workshop", "cost": 24, "hours": 2,
     "tools": ["saw", "drill"],
     "why": "Cheapest project here. Uses the offcuts you were going to throw out."},

    # --- creative / writing (the BioVega lane) --------------------------
    {"id": "C01", "name": "Outline one chapter", "cat": "creative", "cost": 0, "hours": 2,
     "tools": [],
     "why": "One chapter, not the book. The book is the sum of one chapter done twice a week."},
    {"id": "C02", "name": "Mock a cover", "cat": "creative", "cost": 0, "hours": 2,
     "tools": [],
     "why": "A cover you can look at makes the thing real. Nobody finishes a book they cannot see."},
    {"id": "C03", "name": "Write 500 words on what you already know", "cat": "creative", "cost": 0, "hours": 1,
     "tools": [],
     "why": "You have more usable knowledge than most people who write books. Prove it once."},

    # --- earn-from-home ------------------------------------------------
    {"id": "E01", "name": "Photograph one finished piece properly", "cat": "earn", "cost": 0, "hours": 1,
     "tools": [],
     "why": "Whatever you build is inventory until it is photographed. Then it is a listing."},
    {"id": "E02", "name": "List one build for sale", "cat": "earn", "cost": 0, "hours": 1,
     "tools": [],
     "why": "A pallet table sells for $120-200. Cost you $47 and an afternoon."},
]


def load():
    if not os.path.exists(INV):
        return {"tools": [], "budget": 150, "done": []}
    with open(INV, encoding="utf-8") as fh:
        return json.load(fh)


def save(inv):
    with open(INV, "w", encoding="utf-8") as fh:
        json.dump(inv, fh, indent=2)


def score(p, inv):
    """Can they build it, and with how much friction?"""
    owned = {t.lower() for t in inv["tools"]}
    missing = [t for t in p["tools"] if t.lower() not in owned]
    over = p["cost"] > inv["budget"]
    return missing, over


def eligible(inv):
    out = []
    for p in CATALOG:
        if p["id"] in inv.get("done", []):
            continue
        missing, over = score(p, inv)
        if over:
            continue
        out.append((len(missing), p, missing))
    out.sort(key=lambda x: (x[0], x[1]["cost"]))
    return out


def cmd_seed(args):
    if not os.path.exists(INV):
        save({"tools": ["saw", "drill", "sander", "hammer", "wrench set"],
              "budget": 150, "done": []})
        print("starter inventory written - %s" % INV)
    print("%d projects in the catalog, capped at your budget." % len(CATALOG))
    return 0


def cmd_this(args):
    inv = load()
    pool = eligible(inv)
    if not pool:
        print("Nothing fits your budget of $%d and your tools." % inv["budget"])
        print("Try: projects.py budget 250   or   projects.py own <tool>")
        return 1

    wk = date.today().isocalendar()[1]
    best = [p for p in pool if p[0] == 0]
    pick = (best or pool)[wk % len(best or pool)]
    _, p, missing = pick

    print("=" * 62)
    print("  THIS WEEKEND - %s" % date.today().strftime("%A, %B %d"))
    print("=" * 62)
    print("\n  %s" % p["name"])
    print("  $%d in materials, about %d hours" % (p["cost"], p["hours"]))
    print("\n  %s" % p["why"])
    if p["tools"]:
        have = [t for t in p["tools"] if t not in missing]
        print("\n  Tools: %s" % (", ".join(have) if have else "-"))
    if missing:
        print("  Missing: %s  (borrow, or pick another)" % ", ".join(missing))
    print("\n  One project. Not a lifestyle change.\n")
    return 0


def cmd_match(args):
    inv = load()
    budget = int(args[0]) if args else inv["budget"]
    inv["budget"] = budget
    print("  Budget $%d, tools: %s\n" % (budget, ", ".join(inv["tools"]) or "none"))
    rows = [(len(score(p, inv)[0]), p, score(p, inv)[0]) for p in CATALOG
            if p["cost"] <= budget and p["id"] not in inv.get("done", [])]
    rows.sort(key=lambda x: (x[0], x[1]["cost"]))
    for n, p, missing in rows:
        flag = "ready" if n == 0 else "needs " + ",".join(missing)
        print("  %-34s $%3d  %5.1fh  %s" % (p["name"][:34], p["cost"], p["hours"], flag))
    print("\n  %d of %d buildable with what you own." % (sum(1 for r in rows if r[0] == 0), len(rows)))
    return 0


def cmd_own(args):
    inv = load()
    for t in args:
        if t.lower() not in {x.lower() for x in inv["tools"]}:
            inv["tools"].append(t)
    save(inv)
    print("tools: %s" % ", ".join(inv["tools"]))
    return 0


def cmd_budget(args):
    if not args:
        print("usage: projects.py budget <dollars>")
        return 1
    inv = load()
    inv["budget"] = int(args[0])
    save(inv)
    print("budget ceiling: $%d" % inv["budget"])
    return 0


COMMANDS = {"seed": cmd_seed, "this": cmd_this, "match": cmd_match,
            "own": cmd_own, "budget": cmd_budget}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 0 if len(argv) < 2 else 1
    return COMMANDS[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
