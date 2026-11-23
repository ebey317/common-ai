#!/usr/bin/env python3
"""
COMMON AI - read the standards back
===================================
  python3 standards.py            # every rule, its value, its source
  python3 standards.py --open     # only rules with no source (unconfirmed)

The point of this file is challenge. A rule the system obeys but cannot explain
is a rule nobody can correct. Everything suggest.py, ledger.py and profile.py
enforce gets listed here with where it came from, so a wrong rule can be argued
with instead of silently followed.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "standards.json")


def walk(node, path=""):
    """Yield (path, value, source, why) for every leaf rule."""
    if isinstance(node, dict):
        if "value" in node:
            yield (path, node.get("value"), node.get("source"), node.get("why"))
            return
        for k, v in node.items():
            if k.startswith("_"):
                continue
            yield from walk(v, "%s.%s" % (path, k) if path else k)
    elif isinstance(node, list):
        yield (path, node, None, None)


def fmt(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v is None:
        return "(none)"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def main(argv):
    only_open = "--open" in argv
    try:
        with open(PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        print("cannot read standards.json: %s" % exc)
        return 1

    rules = list(walk(data))
    sourced = [r for r in rules if r[2]]
    unsourced = [r for r in rules if not r[2]]

    if only_open:
        if not unsourced:
            print("Every rule carries a source. Nothing is being obeyed anonymously.")
            return 0
        print("RULES WITH NO SOURCE - these are being enforced on nobody's authority:\n")
        for p, v, _, _ in unsourced:
            print("  %-40s %s" % (p, fmt(v)))
        return 0

    print("=" * 74)
    print("  YOUR STANDARDS - %d rules" % len(rules))
    print("=" * 74)
    section = None
    for p, v, src, why in rules:
        top = p.split(".")[0]
        if top != section:
            section = top
            print("\n  " + top.upper().replace("_", " "))
        print("\n    %s" % p.split(".", 1)[-1].replace(".", " / "))
        print("      value  : %s" % fmt(v))
        print("      source : %s" % (src or "!! NO SOURCE !!"))

    print("\n" + "-" * 74)
    print("  %d of %d rules carry a source." % (len(sourced), len(rules)))
    if unsourced:
        print("  %d have none - run with --open to list them." % len(unsourced))
    print("  No module hardcodes a threshold. Change a value here and the")
    print("  behaviour changes without touching code.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
