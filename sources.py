#!/usr/bin/env python3
"""
COMMON AI - sources
===================
Where a person's information already lives. The intake should not ask a question
the documents can answer; it should read them, show the answer back, and ask
"is this right?"

  python3 sources.py where    # what exists, where, reachable or not
  python3 sources.py pull     # extract into prefill.json
  python3 sources.py ledger   # pull Applications Log rows into ledger.csv

Rule: extract only what is literally there. If a value cannot be read exactly,
leave it blank and let the intake ask. A guessed prefill is worse than a question.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(HERE, "profile.json")
PREFILL = os.path.join(HERE, "prefill.json")
LEDGER = os.path.join(HERE, "ledger.csv")
TOKEN = os.path.expanduser("~/.hermes/google_token.json")

# ---------------------------------------------------------------- registry
SOURCES = [
    {"id": "profile", "kind": "local", "label": "Profile (structured)",
     "path": PROFILE, "gives": "identity, employment, buckets, tools, budget"},
    {"id": "ai_query", "kind": "gdoc", "label": "AI Query - job application reference",
     "doc": "1IhFP75OAehPMojsxyi1WOrb5BI2YSxfQad6-cesof74",
     "gives": "job filters, pay floor, radius, education, certs, criminal-history handling"},
    {"id": "app_log", "kind": "gdoc", "label": "Applications Log",
     "doc": "1Dp1IPUSXoY7mXM1FNTMtpfNZdGH_YxRqvs3bYaj6Bpc",
     "gives": "application history, do-not-reapply list"},
    {"id": "resume_ai", "kind": "local", "label": "AI resume",
     "path": os.path.expanduser("~/workspace/Your Name - AI Engineer Resume.md"),
     "gives": "tech domain, GitHub, website, project list"},
    {"id": "resume_trade", "kind": "local", "label": "HVAC / trade resume",
     "path": os.path.expanduser("~/.config/libreoffice/4/user/backup/resume_final.docx.bak"),
     "gives": "trade domain history (fallback - profile.json wins if both have it)"},
]


# ---------------------------------------------------------------- helpers
def _token():
    with open(TOKEN, encoding="utf-8") as fh:
        return json.load(fh)["token"]


def read_doc(doc_id):
    u = "https://docs.googleapis.com/v1/documents/" + doc_id
    req = urllib.request.Request(u, headers={"Authorization": "Bearer " + _token()})
    doc = json.loads(urllib.request.urlopen(req).read())
    out = []

    def walk(el):
        if "paragraph" in el:
            for x in el["paragraph"].get("elements", []):
                if "textRun" in x:
                    out.append(x["textRun"]["content"])
        if "table" in el:
            for row in el["table"].get("tableRows", []):
                for c in row.get("tableCells", []):
                    for cc in c.get("content", []):
                        walk(cc)
        if "body" in el:
            for cc in el["body"].get("content", []):
                walk(cc)

    walk(doc)
    return "".join(out)


def bullets_after(text, heading):
    """Bullet lines after a heading. Docs API strips list asterisks, so we
    also accept leading '-', and we stop at the next SECTION HEADING:."""
    i = text.find(heading)
    if i < 0:
        return []
    items = []
    for line in text[i + len(heading):].split("\n"):
        s = line.strip()
        if not s:
            if items:
                break
            continue
        if s.endswith(":") and (s.isupper() or "EXCLUDE" in s.upper() or "IN-FIT" in s.upper()):
            break
        s = re.sub(r"^[\*\u2022\-]\s*", "", s).strip()
        if s:
            items.append(s)
    return items


def first_int(patterns, text):
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1).replace(",", ""))
    return None


# ---------------------------------------------------------------- commands
def cmd_where(args):
    print("=" * 68)
    print("  WHERE YOUR INFORMATION LIVES")
    print("=" * 68)
    for s in SOURCES:
        if s["kind"] == "local":
            ok = os.path.exists(s["path"])
            loc = s["path"].replace(os.path.expanduser("~"), "~")
            glyph = "OK  " if ok else "MISS"
        else:
            try:
                read_doc(s["doc"])
                ok, loc, glyph = True, "drive: " + s["doc"][:18] + "...", "OK  "
            except Exception as exc:
                ok, loc, glyph = False, "drive: " + s["doc"][:18] + "...", "FAIL"
                loc += "  (%s)" % type(exc).__name__
        print("\n  [%s] %s" % (glyph, s["label"]))
        print("         %s" % loc)
        print("         gives: %s" % s["gives"])
    return 0


def cmd_pull(args):
    pre = {}
    notes = []

    def put(key, value, source):
        if value in (None, "", [], 0):
            return
        pre[key] = {"value": value, "source": source}

    # ---- 1. structured profile wins for anything it holds
    prof = {}
    if os.path.exists(PROFILE):
        with open(PROFILE, encoding="utf-8") as fh:
            prof = json.load(fh)
    per = prof.get("personal", {})
    for k in ("full_name", "phone", "email", "address_line1", "city", "state", "zip", "github"):
        put("personal." + k, per.get(k), "profile")
    inv = prof.get("inventory", {})
    put("inventory.tools", inv.get("tools"), "profile")
    put("inventory.budget", inv.get("budget"), "profile")

    # ---- 2. AI resume markdown: website and GitHub
    ai_res = next((s for s in SOURCES if s["id"] == "resume_ai"), None)
    if ai_res and os.path.exists(ai_res["path"]):
        txt = open(ai_res["path"], encoding="utf-8", errors="ignore").read()
        m = re.search(r"(yourhandle\.github\.io)", txt)
        if m:
            put("personal.website", "https://" + m.group(1), "resume_ai")
        m = re.search(r"github\.com/([A-Za-z0-9_-]+)", txt)
        if m:
            put("personal.github", "github.com/" + m.group(1), "resume_ai")

    # ---- 3. AI Query doc: the job filters, pay floor, radius, status
    try:
        q = read_doc("1IhFP75OAehPMojsxyi1WOrb5BI2YSxfQad6-cesof74")
        fit = bullets_after(q, "IN-FIT (apply to these):")
        avoid = bullets_after(q, "HARD EXCLUDES (never apply):")
        put("situation.target_jobs", fit, "ai_query")
        put("situation.wont_do", avoid, "ai_query")
        put("situation.pay_floor", first_int([r"\$([0-9,]+)\s*/\s*(?:year|yr)", r"\$([0-9,]{5,})"], q), "ai_query")
        put("situation.travel_miles", first_int([r"surrounding\s*~?\s*(\d{1,3})\s*miles"], q), "ai_query")
        if re.search(r"actively\s+job\s+hunting", q, re.I):
            put("situation.status", "unemployed", "ai_query")
        notes.append("ai_query read: %d chars" % len(q))
    except Exception as exc:
        notes.append("ai_query UNREADABLE: %s: %s" % (type(exc).__name__, exc))

    with open(PREFILL, "w", encoding="utf-8") as fh:
        json.dump(pre, fh, indent=2, ensure_ascii=False)

    print("=" * 68)
    print("  PREFILL - %d answers found without asking" % len(pre))
    print("=" * 68)
    for k in sorted(pre):
        v = pre[k]["value"]
        shown = ", ".join(v) if isinstance(v, list) else str(v)
        if len(shown) > 56:
            shown = shown[:53] + "..."
        print("  %-28s %-56s  [%s]" % (k, shown, pre[k]["source"]))
    print("\n  still has to be asked: health, household, spending, hobbies")
    print("  (those were never written down anywhere - no source can invent them)")
    for n in notes:
        print("  note: %s" % n)
    return 0


def cmd_ledger(args):
    """Pull 'Company — Role —' rows out of the Applications Log into ledger.csv."""
    try:
        log = read_doc("1Dp1IPUSXoY7mXM1FNTMtpfNZdGH_YxRqvs3bYaj6Bpc")
    except Exception as exc:
        print("cannot read Applications Log: %s" % exc)
        return 1
    rows = re.findall(r"^([A-Z0-9][^\u2014\n]{2,45}) \u2014 ([^\u2014\n]{4,70}) \u2014 ([^\n]{0,80})", log, re.M)
    good = [(c.strip(), r.strip(), tail.strip()) for c, r, tail in rows
            if "ZipRecruiter" in tail or "Indeed" in tail or "Honest" in tail or "20" in tail]
    print("parsed %d candidate rows, %d look like real applications" % (len(rows), len(good)))
    for c, r, t in good[:8]:
        print("  %-34s %-40s %s" % (c[:34], r[:40], t[:28]))
    print("\n(ledger import left manual for now - confirm the parse is clean first)")
    return 0


COMMANDS = {"where": cmd_where, "pull": cmd_pull, "ledger": cmd_ledger}


def main(argv):
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 0 if len(argv) < 2 else 1
    return COMMANDS[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
